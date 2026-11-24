"""The bot's second message about a post the user forwarded: the rating result
(functional spec 012, 2.2), sent as a reply to the forwarded message.

The run records one `ForwardResult` per rated forwarded post (in
`service._apply_evaluation`, only for posts with an unreported
`forwarded_posts` row); after the run, next to the alerts, each result is
sent and its row gets `reported_at`.

Same invariant as `service.py`: no network I/O while a transaction is open
(read → send → short write).

- `TelegramError` (blocked bot, chat gone, ...): logged by `send_text`;
  `reported_at` is still set (no retry loop).
- No bot (worker without a token): the result is only logged and
  `reported_at` stays NULL, so the row still shows the reply never went out.
  Nothing resends it later; the row is deleted by the 30-day cleanup.
- The chat is no longer linked to the user: nothing is sent, `reported_at`
  is set.
"""

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TypeAlias

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot

from app.core.telegram_send import SleepFn, send_text
from app.discovery.alerts import clip_field
from app.models.forwarded_post import ForwardedPost
from app.models.telegram_link import TelegramLink

__all__ = [
    "ForwardResult",
    "ForwardResultKind",
    "format_forward_reply",
    "send_forward_replies",
]

logger = logging.getLogger(__name__)

SessionFactory: TypeAlias = Callable[[], AsyncSession]
Clock: TypeAlias = Callable[[], datetime]

_FIT_LABELS = {"high": "High", "medium": "Medium", "low": "Low"}


class ForwardResultKind(StrEnum):
    MATCHED = "matched"  # single vacancy, new card
    MERGED = "merged"  # single vacancy, merged into a card already in the Inbox
    DIGEST = "digest"  # digest with at least one matching vacancy
    NONE = "none"  # no matching vacancy (single or digest)
    NOT_VACANCY = "not_vacancy"
    UNRATABLE = "unratable"  # no valid AI verdict after MAX_EVAL_ATTEMPTS


@dataclass(frozen=True, slots=True, kw_only=True)
class ForwardResult:
    """The rating result of one forwarded post.

    `fit`/`title`/`company`: the card (MATCHED, MERGED). `matched`/`total`:
    matching vacancies (new cards + merged) and vacancies in the post (DIGEST).
    """

    user_id: str
    external_key: str
    kind: ForwardResultKind
    fit: str | None = None
    title: str | None = None
    company: str | None = None
    matched: int = 0
    total: int = 0


def format_forward_reply(result: ForwardResult) -> str:
    """The functional spec 2.2 text for `result`."""
    role = clip_field(result.title or "") or "Unknown role"
    company = clip_field(result.company or "") or "Unknown company"
    match result.kind:
        case ForwardResultKind.DIGEST:
            return (
                f"✅ {result.matched} of {result.total} vacancies match. "
                "Added to your Inbox."
            )
        case ForwardResultKind.MATCHED:
            fit = _FIT_LABELS.get(result.fit or "", "Unrated")
            return f"✅ Added to your Inbox: {fit} · {role} — {company}"
        case ForwardResultKind.MERGED:
            return f"{role} — {company} is already in your Inbox."
        case ForwardResultKind.NONE:
            return "None of the vacancies in this post match your search."
        case ForwardResultKind.NOT_VACANCY:
            return "This post doesn't look like a vacancy."
        case ForwardResultKind.UNRATABLE:
            return "Jobbi couldn't rate this post."


async def send_forward_replies(
    session_factory: SessionFactory,
    bot: Bot | None,
    results: Sequence[ForwardResult],
    clock: Clock,
    *,
    sleep: SleepFn = asyncio.sleep,
) -> int:
    """Reply to each forwarded post with its result; returns messages sent."""
    sent = 0
    for result in results:
        try:
            if await _reply(session_factory, bot, result, clock, sleep):
                sent += 1
        except SQLAlchemyError:
            # One post's database trouble must not stop the other replies.
            logger.exception(
                "Reply about forwarded post %s failed", result.external_key
            )
    return sent


@dataclass(frozen=True, slots=True)
class _Target:
    row_id: str
    chat_id: int
    message_id: int
    is_linked: bool


async def _reply(
    session_factory: SessionFactory,
    bot: Bot | None,
    result: ForwardResult,
    clock: Clock,
    sleep: SleepFn,
) -> bool:
    if bot is None:
        logger.info(
            "Forwarded post %s of user %s rated: %s (no bot, reply not sent)",
            result.external_key,
            result.user_id,
            result.kind,
        )
        return False
    target = await _load_target(session_factory, result)
    if target is None:
        return False  # reported already, or cleaned up
    is_sent = False
    if target.is_linked:
        is_sent = await send_text(
            bot,
            target.chat_id,
            format_forward_reply(result),
            sleep=sleep,
            reply_to=target.message_id,
        )
        if not is_sent:
            logger.warning(
                "Reply about forwarded post %s could not be sent", result.external_key
            )
    else:
        logger.info(
            "Chat of forwarded post %s is no longer linked; no reply",
            result.external_key,
        )
    async with session_factory() as session, session.begin():
        await session.execute(
            update(ForwardedPost)
            .where(
                ForwardedPost.id == target.row_id, ForwardedPost.reported_at.is_(None)
            )
            .values(reported_at=clock())
        )
    return is_sent


async def _load_target(
    session_factory: SessionFactory, result: ForwardResult
) -> _Target | None:
    async with session_factory() as session:
        row = (
            await session.execute(
                select(
                    ForwardedPost.id, ForwardedPost.chat_id, ForwardedPost.message_id
                ).where(
                    ForwardedPost.user_id == result.user_id,
                    ForwardedPost.external_key == result.external_key,
                    ForwardedPost.reported_at.is_(None),
                )
            )
        ).one_or_none()
        if row is None:
            return None
        row_id, chat_id, message_id = row
        linked = await session.scalar(
            select(TelegramLink.id).where(
                TelegramLink.user_id == result.user_id,
                TelegramLink.chat_id == chat_id,
            )
        )
    return _Target(
        row_id=row_id,
        chat_id=chat_id,
        message_id=message_id,
        is_linked=linked is not None,
    )
