"""Handler for /summary command."""

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.handlers.dialog import NOT_LINKED_MESSAGE
from app.core.database import async_session
from app.services.summary_service import build_summary
from app.services.telegram_service import get_link_by_chat


async def handle_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the pipeline summary to the requesting chat."""
    if update.effective_chat is None:
        return
    chat_id = update.effective_chat.id

    async with async_session() as db:
        link = await get_link_by_chat(db, chat_id)
        if link is None:
            text = NOT_LINKED_MESSAGE
        else:
            text = await build_summary(db, link.user_id)

    await context.bot.send_message(chat_id=chat_id, text=text)
