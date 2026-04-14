"""Handlers for /start command and connection code verification."""

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

    async with async_session() as db:
        link = await verify_and_consume_code(db, normalized, chat_id, username)

    if link is None:
        await context.bot.send_message(chat_id=chat_id, text=INVALID_CODE_MESSAGE)
    else:
        await context.bot.send_message(chat_id=chat_id, text=LINK_SUCCESS_MESSAGE)

    return True
