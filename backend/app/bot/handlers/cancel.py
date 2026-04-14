"""Handler for /cancel command."""

from sqlalchemy import delete
from telegram import Update
from telegram.ext import ContextTypes

from app.core.database import async_session
from app.models.telegram_conversation import TelegramConversation


CANCEL_MESSAGE = "🚫 Cancelled."
NOTHING_TO_CANCEL_MESSAGE = "There's nothing in progress."


async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear the user's conversation state."""
    if update.effective_chat is None:
        return
    chat_id = update.effective_chat.id

    async with async_session() as db:
        result = await db.execute(
            delete(TelegramConversation).where(
                TelegramConversation.chat_id == chat_id
            )
        )
        await db.commit()
        deleted = result.rowcount or 0

    message = CANCEL_MESSAGE if deleted > 0 else NOTHING_TO_CANCEL_MESSAGE
    await context.bot.send_message(chat_id=chat_id, text=message)
