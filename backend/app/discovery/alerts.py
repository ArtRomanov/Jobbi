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
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot

from app.core.config import get_settings
from app.core.telegram_send import SleepFn, send_text
from app.models.telegram_link import TelegramLink
from app.models.vacancy import Vacancy

__all__ = [
    "MAX_ALERT_LINES",
    "AlertCard",
    "default_inbox_url",
    "format_alert",
    "send_run_alerts",
]

logger = logging.getLogger(__name__)

MAX_ALERT_LINES = 10
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


def _line(card: AlertCard) -> str:
    fit = _FIT_LABELS.get(card.fit or "", "Unrated")
    role = (card.title or "").strip() or "Unknown role"
    company = (card.company or "").strip() or "Unknown company"
    return f"{fit} · {role} — {company}"


def format_alert(cards: Sequence[AlertCard], inbox_url: str) -> str:
    """The alert text (functional spec 2.4). `cards` must not be empty."""
    count = len(cards)
    header = "🔎 1 new vacancy" if count == 1 else f"🔎 {count} new vacancies"
    ordered = _ordered(cards)
    lines = [header, "", *(_line(card) for card in ordered[:MAX_ALERT_LINES])]
    if count > MAX_ALERT_LINES:
        lines.append(f"+{count - MAX_ALERT_LINES} more in Inbox")
    lines.extend(["", f"🔗 Open Inbox: {inbox_url}"])
    return "\n".join(lines)


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
        cards, chat_id = await _load(session_factory, user_id, card_ids)
        if cards and bot is not None and chat_id is not None:
            if await send_text(bot, chat_id, format_alert(cards, url), sleep=sleep):
                sent += 1
                logger.info("Alert sent to user %s: %d card(s)", user_id, len(cards))
            else:
                logger.warning("Alert for user %s could not be sent", user_id)
        await _mark_handled(session_factory, user_id, card_ids, clock())
    return sent


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
