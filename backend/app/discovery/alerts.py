"""Grouped Telegram alerts for the cards a discovery run made `new`.

Per user per run, only cards not yet handled:
- cards from hourly checks: one message ("🔎 N new vacancies");
- cards from a source's first scan (backlog #30), grouped by source: one
  message per source when at most `MAX_SEPARATE_SOURCES` sources have
  matches, else one combined message. A first-scan card rated in a later run
  (daily cap, per-source cap, AI down) is summarised in that run. A card whose
  source was removed is handled without a message.

`alert_handled_at` is set on every loaded card in every case (no bot, no
Telegram link, send failed), so linking Telegram later never brings a message
about old cards, and a card is never announced twice.

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
from urllib.parse import urlencode

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot

from app.core.config import get_settings
from app.core.telegram_send import SleepFn, send_text
from app.models.telegram_link import TelegramLink
from app.models.vacancy import Vacancy
from app.models.vacancy_source import VacancySource
from app.services.vacancy_service import source_key

__all__ = [
    "MAX_ALERT_LINES",
    "MAX_FIELD_CHARS",
    "MAX_MESSAGE_CHARS",
    "MAX_SEPARATE_SOURCES",
    "MESSAGE_GAP_S",
    "AlertCard",
    "SourceCards",
    "clip_field",
    "default_inbox_url",
    "first_scan_messages",
    "format_alert",
    "format_source_alert",
    "format_sources_summary",
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
# First-scan matches from more sources than this go into one combined message.
MAX_SEPARATE_SOURCES = 3
# Pause between consecutive messages to the same user.
MESSAGE_GAP_S = 1.0
_TELEGRAM_KIND = "telegram"

SessionFactory: TypeAlias = Callable[[], AsyncSession]
Clock: TypeAlias = Callable[[], datetime]


@dataclass(frozen=True, slots=True, kw_only=True)
class AlertCard:
    fit: str | None
    title: str | None
    company: str | None
    posted_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceCards:
    """First-scan cards of one source (`name` is the source's display name)."""

    kind: str
    handle: str
    name: str
    cards: tuple[AlertCard, ...]

    @property
    def key(self) -> str:
        return source_key(self.kind, self.handle)


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


def clip_field(value: str, limit: int = MAX_FIELD_CHARS) -> str:
    """One line of untrusted text for a bot message: control characters
    dropped, whitespace collapsed, cut to `limit`."""
    value = _strip_controls(value)
    value = " ".join(value.split())  # no line breaks inside one alert line
    return value if len(value) <= limit else f"{value[: limit - 1].rstrip()}…"


def _line(card: AlertCard) -> str:
    fit = _FIT_LABELS.get(card.fit or "", "Unrated")
    role = clip_field(card.title or "") or "Unknown role"
    company = clip_field(card.company or "") or "Unknown company"
    return f"{fit} · {role} — {company}"


def _matching(count: int) -> str:
    return "1 matching vacancy" if count == 1 else f"{count} matching vacancies"


def _source_name(source: SourceCards) -> str:
    # Channel titles come from strangers: same cleaning as card fields.
    return clip_field(source.name) or clip_field(source.handle) or "Unknown source"


def _fit_to_limit(compose: Callable[[int], str], shown: int, max_chars: int) -> str:
    """`compose(shown)` with as many card lines as fit in `max_chars`."""
    text = compose(shown)
    while shown > 0 and _telegram_len(text) > max_chars:
        shown -= 1
        text = compose(shown)
    # Last resort (an absurdly long Inbox URL): a cut message beats none.
    while _telegram_len(text) > max_chars:
        text = text[:-1]
    return text


def format_alert(
    cards: Sequence[AlertCard],
    inbox_url: str,
    *,
    header: str | None = None,
    max_chars: int = MAX_MESSAGE_CHARS,
) -> str:
    """The alert text (functional spec 2.4). `cards` must not be empty.

    `header` replaces "🔎 N new vacancies" (a source's first-scan summary).
    If the text would exceed `max_chars`, trailing card lines are dropped and
    counted in "+M more in Inbox"; the header and the Inbox link always stay.
    """
    count = len(cards)
    if header is None:
        header = "🔎 1 new vacancy" if count == 1 else f"🔎 {count} new vacancies"
    card_lines = [_line(card) for card in _ordered(cards)[:MAX_ALERT_LINES]]
    link = f"🔗 Open Inbox: {inbox_url}"

    def compose(shown: int) -> str:
        lines = [header, "", *card_lines[:shown]]
        if count > shown:
            lines.append(f"+{count - shown} more in Inbox")
        lines.extend(["", link])
        return "\n".join(lines)

    return _fit_to_limit(compose, len(card_lines), max_chars)


def format_source_alert(
    source: SourceCards, inbox_url: str, *, max_chars: int = MAX_MESSAGE_CHARS
) -> str:
    """First-scan summary of one source; its Inbox link filters by the source.

    The header says "first scan", not "new": a big first scan is rated over
    several runs (per-source and daily caps) and each run sends its part.
    """
    noun = "channel" if source.kind == _TELEGRAM_KIND else "source"
    name = _source_name(source)
    header = f"🔎 First scan of {noun} {name}: {_matching(len(source.cards))}"
    link = f"{inbox_url}?{urlencode({'source': source.key})}"
    return format_alert(source.cards, link, header=header, max_chars=max_chars)


def format_sources_summary(
    sources: Sequence[SourceCards],
    inbox_url: str,
    *,
    max_chars: int = MAX_MESSAGE_CHARS,
) -> str:
    """First-scan summary of several sources in one message: per source a
    "<name> (N)" line and its card lines, at most `MAX_ALERT_LINES` card lines
    in all (in `sources` order); the rest is counted in "+M more in Inbox"."""
    total = sum(len(source.cards) for source in sources)
    header = f"🔎 First scans: {_matching(total)} from {len(sources)} sources"
    sections: list[tuple[str, list[str]]] = []
    budget = MAX_ALERT_LINES
    for source in sources:
        lines = [_line(card) for card in _ordered(source.cards)[:budget]]
        budget -= len(lines)
        sections.append((f"{_source_name(source)} ({len(source.cards)})", lines))
    link = f"🔗 Open Inbox: {inbox_url}"

    def compose(shown: int) -> str:
        lines = [header]
        left = shown
        for title, card_lines in sections:
            taken = card_lines[:left]
            if not taken:
                break
            lines.extend(["", title, *taken])
            left -= len(taken)
        if total > shown:
            lines.append(f"+{total - shown} more in Inbox")
        lines.extend(["", link])
        return "\n".join(lines)

    shown = sum(len(card_lines) for _, card_lines in sections)
    return _fit_to_limit(compose, shown, max_chars)


def first_scan_messages(sources: Sequence[SourceCards], inbox_url: str) -> list[str]:
    """One message per source, or one combined message for more than
    `MAX_SEPARATE_SOURCES` sources. Sources with the most matches first."""
    ordered = sorted(
        (source for source in sources if source.cards),
        key=lambda source: (-len(source.cards), _source_name(source).casefold()),
    )
    if len(ordered) > MAX_SEPARATE_SOURCES:
        return [format_sources_summary(ordered, inbox_url)]
    return [format_source_alert(source, inbox_url) for source in ordered]


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

    `run_card_ids_by_user` may include cards that have left the Inbox since
    or were handled already; they are filtered here. Returns the number of
    messages sent (a user may get several: hourly + first-scan summaries).
    """
    url = inbox_url or default_inbox_url()
    sent = 0
    for user_id, raw_ids in run_card_ids_by_user.items():
        card_ids = list(dict.fromkeys(raw_ids))
        if not card_ids:
            continue
        try:
            sent += await _alert_user(
                session_factory, bot, user_id, card_ids, clock, url, sleep
            )
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
) -> int:
    """Send (maybe) and mark handled; returns the number of messages sent."""
    sent = 0
    loaded = await _load(session_factory, user_id, card_ids)
    if bot is not None and loaded.chat_id is not None:
        texts = first_scan_messages(loaded.first_scan, inbox_url)
        if loaded.hourly:
            texts.insert(0, format_alert(loaded.hourly, inbox_url))
        for index, text in enumerate(texts):
            if index:
                # Several messages to one chat: a short gap, so a burst does
                # not hit Telegram's flood limit (a second RetryAfter loses it).
                await sleep(MESSAGE_GAP_S)
            if await send_text(bot, loaded.chat_id, text, sleep=sleep):
                sent += 1
            else:
                logger.warning("Alert for user %s could not be sent", user_id)
        if sent:
            logger.info(
                "Alerts sent to user %s: %d message(s); %d hourly card(s), "
                "%d first-scan source(s)",
                user_id,
                sent,
                len(loaded.hourly),
                len(loaded.first_scan),
            )
    await _mark_handled(session_factory, user_id, card_ids, clock())
    return sent


@dataclass(frozen=True, slots=True, kw_only=True)
class _Loaded:
    hourly: list[AlertCard]
    first_scan: list[SourceCards]
    chat_id: int | None


async def _load(
    session_factory: SessionFactory, user_id: str, card_ids: list[str]
) -> _Loaded:
    hourly: list[AlertCard] = []
    by_source: dict[str, tuple[str, str, str, list[AlertCard]]] = {}
    async with session_factory() as session:
        rows = await session.execute(
            select(
                Vacancy.fit,
                Vacancy.title,
                Vacancy.company,
                Vacancy.posted_at,
                Vacancy.from_initial_scan,
                VacancySource.id.label("source_id"),
                VacancySource.kind,
                VacancySource.handle,
                VacancySource.display_name,
            )
            .outerjoin(
                VacancySource,
                (VacancySource.id == Vacancy.source_id)
                & (VacancySource.user_id == Vacancy.user_id),
            )
            .where(
                Vacancy.user_id == user_id,
                Vacancy.id.in_(card_ids),
                Vacancy.alert_handled_at.is_(None),
                Vacancy.state.in_(_ALERTABLE_STATES),
            )
        )
        for row in rows:
            alert_card = AlertCard(
                fit=row.fit,
                title=row.title,
                company=row.company,
                posted_at=row.posted_at,
            )
            if not row.from_initial_scan:
                hourly.append(alert_card)
            elif row.source_id is not None:
                group = by_source.setdefault(
                    row.source_id, (row.kind, row.handle, row.display_name, [])
                )
                group[3].append(alert_card)
            # Else a first-scan card whose source was removed: handled, unsent.
        chat_id = await session.scalar(
            select(TelegramLink.chat_id).where(TelegramLink.user_id == user_id)
        )
    first_scan = [
        SourceCards(kind=kind, handle=handle, name=name, cards=tuple(cards))
        for kind, handle, name, cards in by_source.values()
    ]
    return _Loaded(hourly=hourly, first_scan=first_scan, chat_id=chat_id)


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
