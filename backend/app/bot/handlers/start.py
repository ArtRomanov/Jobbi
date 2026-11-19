"""Handlers for /start command and connection code verification."""

import time
from collections import deque
from collections.abc import Callable

from telegram import Update
from telegram.ext import ContextTypes

from app.core.database import async_session
from app.services.telegram_service import (
    get_link_by_chat,
    verify_and_consume_code,
)


START_MESSAGE = (
    "👋 Welcome to Jobbi!\n\n"
    "Please send me your 6-character connection code from the Jobbi Settings page."
)

ALREADY_LINKED_MESSAGE = (
    "✅ You're already connected! Forward a job posting to add it, "
    "or send /summary to see your pipeline."
)

LINK_SUCCESS_MESSAGE = (
    "🎉 You're connected!\n\n"
    "Now you can:\n"
    "• Forward job postings to create applications\n"
    "• Send /summary for an instant pipeline overview\n"
    "• Send /cancel to abort any in-progress conversation"
)

INVALID_CODE_MESSAGE = (
    "❌ That code is invalid, expired, or already used.\n"
    "Please generate a new code from the Jobbi Settings page."
)

TOO_MANY_ATTEMPTS_MESSAGE = (
    "⏳ Too many wrong codes. Please wait 15 minutes and try again."
)

MAX_FAILED_CODES = 5
FAILED_CODE_WINDOW_SECONDS = 15 * 60


class FailedCodeLimiter:
    """In-memory sliding-window counter of failed code guesses per chat.

    After `max_failures` failures within `window_seconds` a chat is blocked:
    its code messages are not checked against the database, it gets one
    "too many attempts" reply, then silence until old failures age out. This
    stops brute-forcing and keeps a flood of guesses from pushing the bot into
    Telegram's global rate limit (which would also delay daily summaries).
    State is per process and resets on restart, which is acceptable here.
    """

    def __init__(
        self,
        max_failures: int = MAX_FAILED_CODES,
        window_seconds: float = FAILED_CODE_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_failures = max_failures
        self._window = window_seconds
        self._clock = clock
        self._failures: dict[int, deque[float]] = {}
        self._warned: set[int] = set()

    def _prune(self, chat_id: int) -> deque[float] | None:
        stamps = self._failures.get(chat_id)
        if stamps is None:
            return None
        cutoff = self._clock() - self._window
        while stamps and stamps[0] <= cutoff:
            stamps.popleft()
        if len(stamps) < self._max_failures:
            self._warned.discard(chat_id)
        if not stamps:
            del self._failures[chat_id]
            return None
        return stamps

    def failures(self, chat_id: int) -> int:
        stamps = self._prune(chat_id)
        return 0 if stamps is None else len(stamps)

    def is_blocked(self, chat_id: int) -> bool:
        return self.failures(chat_id) >= self._max_failures

    def claim_warning(self, chat_id: int) -> bool:
        """True the first time it's called for a blocked chat, False after."""
        if chat_id in self._warned:
            return False
        self._warned.add(chat_id)
        return True

    def record_failure(self, chat_id: int) -> None:
        self._prune(chat_id)
        self._failures.setdefault(chat_id, deque()).append(self._clock())

    def reset(self, chat_id: int) -> None:
        self._failures.pop(chat_id, None)
        self._warned.discard(chat_id)


code_attempt_limiter = FailedCodeLimiter()


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    if update.effective_chat is None:
        return
    chat_id = update.effective_chat.id

    async with async_session() as db:
        existing_link = await get_link_by_chat(db, chat_id)
        if existing_link is not None:
            await context.bot.send_message(chat_id=chat_id, text=ALREADY_LINKED_MESSAGE)
            return

    await context.bot.send_message(chat_id=chat_id, text=START_MESSAGE)


async def handle_code_verification(
    update: Update, context: ContextTypes.DEFAULT_TYPE, code: str
) -> bool:
    """Try to verify a message as a connection code.

    Returns True if the message was handled as a code (valid or invalid),
    False if the format doesn't match and the message should be processed otherwise.
    """
    if update.effective_chat is None or update.effective_user is None:
        return False

    # Connection code is 6 alphanumeric uppercase chars
    normalized = code.strip().upper()
    if len(normalized) != 6 or not normalized.isalnum():
        return False

    chat_id = update.effective_chat.id
    username = update.effective_user.username
    limiter = code_attempt_limiter

    if limiter.is_blocked(chat_id):
        if limiter.claim_warning(chat_id):
            await context.bot.send_message(
                chat_id=chat_id, text=TOO_MANY_ATTEMPTS_MESSAGE
            )
        return True

    async with async_session() as db:
        link = await verify_and_consume_code(db, normalized, chat_id, username)

    if link is None:
        limiter.record_failure(chat_id)
        await context.bot.send_message(chat_id=chat_id, text=INVALID_CODE_MESSAGE)
    else:
        limiter.reset(chat_id)
        await context.bot.send_message(chat_id=chat_id, text=LINK_SUCCESS_MESSAGE)

    return True
