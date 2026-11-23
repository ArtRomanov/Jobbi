"""Grouped Telegram alerts for the cards a discovery run made `new`.

One message per user per run, only for cards that are not from a first scan
and not yet handled. `alert_handled_at` is set on those cards in every case
(no bot, no Telegram link, send failed), so linking Telegram later never
brings a message about old cards, and a card is never announced twice.

Same invariant as `service.py`: no network I/O while a transaction is open
(read → send → short write).
"""

import asyncio
import logging
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot

from app.core.config import get_settings
from app.core.telegram_send import SleepFn, send_text
from app.models.telegram_link import TelegramLink
from app.models.vacancy import Vacancy

__all__ = [
    "MAX_ALERT_LINES",
    "MAX_FIELD_CHARS",
    "MAX_MESSAGE_CHARS",
    "AlertCard",
    "default_inbox_url",
    "format_alert",
    "send_run_alerts",
]

logger = logging.getLogger(__name__)

MAX_ALERT_LINES = 10
# Telegram rejects longer messages ("Message is too long"). Telegram counts
# UTF-16 code units (an emoji is 2), see `_telegram_len`.
MAX_MESSAGE_CHARS = 4096
# Role / company are cut to this length so one long title cannot crowd out
# the rest of the alert.
MAX_FIELD_CHARS = 80
# Cards merged, dismissed or added before the alert went out are left out.
_ALERTABLE_STATES = ("new", "seen")
_FIT_LABELS = {"high": "High", "medium": "Medium", "low": "Low"}
_FIT_RANK = {"high": 0, "medium": 1, "low": 2}

SessionFactory: TypeAlias = Callable[[], AsyncSession]
Clock: TypeAlias = Callable[[], datetime]


@dataclass(frozen=True, slots=True, kw_only=True)
class AlertCard:
    fit: str | None
    title: str | None
    company: str | None
    posted_at: datetime


def default_inbox_url() -> str:
    return f"{get_settings().JOBBI_PUBLIC_URL.rstrip('/')}/inbox"


def _ordered(cards: Sequence[AlertCard]) -> list[AlertCard]:
    """Fit high → medium → low (unrated last), then newest first."""
    newest_first = sorted(cards, key=lambda card: card.posted_at, reverse=True)
    # `sorted` is stable, so the newest-first order holds within each fit.
    return sorted(
        newest_first, key=lambda card: _FIT_RANK.get(card.fit or "", len(_FIT_RANK))
    )


def _telegram_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


# Kept although it is a format char: joins emoji sequences such as 👩‍💻.
_ZERO_WIDTH_JOINER = "\u200d"


def _strip_controls(value: str) -> str:
    """Drop control (Cc) and invisible format (Cf) characters.

    Titles and companies come from strangers' posts. Bidi overrides
    (U+202A–U+202E, U+2066–U+2069, U+200E/F, U+061C) could reorder the trusted
    bot's message ("gnp.exe" shown as "exe.png"); zero-width and terminal
    control characters only hide text.
    """
    return "".join(
        char
        for char in value
        if char == _ZERO_WIDTH_JOINER
        or unicodedata.category(char) not in ("Cc", "Cf")
        or char in "\t\n\r"  # whitespace: collapsed below
    )


def _clip(value: str, limit: int = MAX_FIELD_CHARS) -> str:
    value = _strip_controls(value)
    value = " ".join(value.split())  # no line breaks inside one alert line
    return value if len(value) <= limit else f"{value[: limit - 1].rstrip()}…"


def _line(card: AlertCard) -> str:
    fit = _FIT_LABELS.get(card.fit or "", "Unrated")
    role = _clip(card.title or "") or "Unknown role"
    company = _clip(card.company or "") or "Unknown company"
    return f"{fit} · {role} — {company}"


def format_alert(
    cards: Sequence[AlertCard], inbox_url: str, *, max_chars: int = MAX_MESSAGE_CHARS
) -> str:
    """The alert text (functional spec 2.4). `cards` must not be empty.

    If the text would exceed `max_chars`, trailing card lines are dropped and
    counted in "+M more in Inbox"; the header and the Inbox link always stay.
    """
    count = len(cards)
    header = "🔎 1 new vacancy" if count == 1 else f"🔎 {count} new vacancies"
    card_lines = [_line(card) for card in _ordered(cards)[:MAX_ALERT_LINES]]
    link = f"🔗 Open Inbox: {inbox_url}"

    def compose(shown: int) -> str:
        lines = [header, "", *card_lines[:shown]]
        if count > shown:
            lines.append(f"+{count - shown} more in Inbox")
        lines.extend(["", link])
        return "\n".join(lines)

    shown = len(card_lines)
    text = compose(shown)
    while shown > 0 and _telegram_len(text) > max_chars:
        shown -= 1
        text = compose(shown)
    # Last resort (an absurdly long Inbox URL): a cut message beats none.
    while _telegram_len(text) > max_chars:
        text = text[:-1]
    return text


async def send_run_alerts(
    session_factory: SessionFactory,
    bot: Bot | None,
    run_card_ids_by_user: Mapping[str, Iterable[str]],
    clock: Clock,
    *,
    inbox_url: str | None = None,
    sleep: SleepFn = asyncio.sleep,
) -> int:
    """Alert each user about the cards that became `new` in this run.

    `run_card_ids_by_user` may include first-scan cards and cards that have
    left the Inbox since; they are filtered here. Returns the number of
    messages sent.
    """
    url = inbox_url or default_inbox_url()
    sent = 0
    for user_id, raw_ids in run_card_ids_by_user.items():
        card_ids = list(dict.fromkeys(raw_ids))
        if not card_ids:
            continue
        try:
            if await _alert_user(
                session_factory, bot, user_id, card_ids, clock, url, sleep
            ):
                sent += 1
        except SQLAlchemyError:
            # One user's database trouble must not stop the others' alerts.
            logger.exception("Alerts for user %s failed", user_id)
    return sent


async def _alert_user(
    session_factory: SessionFactory,
    bot: Bot | None,
    user_id: str,
    card_ids: list[str],
    clock: Clock,
    inbox_url: str,
    sleep: SleepFn,
) -> bool:
    """Send (maybe) and mark handled; True when a message was sent."""
    is_sent = False
    cards, chat_id = await _load(session_factory, user_id, card_ids)
    if cards and bot is not None and chat_id is not None:
        text = format_alert(cards, inbox_url)
        is_sent = await send_text(bot, chat_id, text, sleep=sleep)
        if is_sent:
            logger.info("Alert sent to user %s: %d card(s)", user_id, len(cards))
        else:
            logger.warning("Alert for user %s could not be sent", user_id)
    await _mark_handled(session_factory, user_id, card_ids, clock())
    return is_sent


async def _load(
    session_factory: SessionFactory, user_id: str, card_ids: list[str]
) -> tuple[list[AlertCard], int | None]:
    async with session_factory() as session:
        rows = await session.execute(
            select(
                Vacancy.fit, Vacancy.title, Vacancy.company, Vacancy.posted_at
            ).where(
                Vacancy.user_id == user_id,
                Vacancy.id.in_(card_ids),
                Vacancy.from_initial_scan.is_(False),
                Vacancy.alert_handled_at.is_(None),
                Vacancy.state.in_(_ALERTABLE_STATES),
            )
        )
        cards = [
            AlertCard(fit=fit, title=title, company=company, posted_at=posted_at)
            for fit, title, company, posted_at in rows
        ]
        chat_id = await session.scalar(
            select(TelegramLink.chat_id).where(TelegramLink.user_id == user_id)
        )
    return cards, chat_id


async def _mark_handled(
    session_factory: SessionFactory,
    user_id: str,
    card_ids: list[str],
    now: datetime,
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            update(Vacancy)
            .where(
                Vacancy.user_id == user_id,
                Vacancy.id.in_(card_ids),
                Vacancy.alert_handled_at.is_(None),
            )
            .values(alert_handled_at=now)
        )
