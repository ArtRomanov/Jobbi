"""Sending Telegram messages with one retry on flood control.

Shared by the bot process (daily summaries, through PTB's `context.bot`) and
the discovery worker (alerts, through a standalone `telegram.Bot`).

Never log the bot token: Bot API URLs embed it, and `Bot.initialize()` puts it
into the `InvalidToken` message. Errors here are logged by class and message
with the token masked, never with a traceback.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import TypeAlias

from telegram import Bot
from telegram.error import Forbidden, RetryAfter, TelegramError

__all__ = ["SleepFn", "describe_error", "send_text", "send_with_retry"]

logger = logging.getLogger(__name__)

SleepFn: TypeAlias = Callable[[float], Awaitable[None]]


async def send_with_retry(
    bot: Bot, chat_id: int, text: str, *, sleep: SleepFn = asyncio.sleep
) -> None:
    """Send once; on flood control wait the requested time and retry once.

    Raises:
        TelegramError: any error of the last attempt (including a second
            `RetryAfter`), for callers that handle errors themselves.
    """
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except RetryAfter as exc:
        delay = exc.retry_after
        seconds = delay.total_seconds() if isinstance(delay, timedelta) else delay
        logger.warning("Flood control: retrying message in %ss", seconds)
        await sleep(seconds)
        await bot.send_message(chat_id=chat_id, text=text)


async def send_text(
    bot: Bot, chat_id: int, text: str, *, sleep: SleepFn = asyncio.sleep
) -> bool:
    """`send_with_retry` that never raises a Telegram error.

    Returns True when the message was sent. A blocked bot / unavailable chat
    (`Forbidden`) and any other `TelegramError` are logged and give False.
    """
    try:
        await send_with_retry(bot, chat_id, text, sleep=sleep)
    except Forbidden:
        logger.warning(
            "Cannot send to chat %s: bot blocked or chat unavailable", chat_id
        )
        return False
    except TelegramError as exc:
        logger.error(
            "Telegram error sending to chat %s: %s", chat_id, describe_error(exc, bot)
        )
        return False
    return True


def describe_error(exc: BaseException, bot: Bot | None = None) -> str:
    """`ClassName: message` with the bot token masked, safe to log."""
    message = f"{type(exc).__name__}: {exc}"
    token = getattr(bot, "token", None)
    if isinstance(token, str) and token:
        message = message.replace(token, "***")
    return message
