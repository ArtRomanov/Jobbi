"""Bot entry point: starts long polling for Telegram updates.

Run with: python -m app.bot
"""

import asyncio
import logging
import sys

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.bot.handlers.cancel import handle_cancel
from app.bot.handlers.dialog import handle_message, handle_status_callback
from app.bot.handlers.jobs import register_summary_jobs
from app.bot.handlers.start import handle_start
from app.bot.handlers.summary import handle_summary
from app.core.config import get_settings
from app.core.worker_logging import configure_logging

__all__ = [
    "add_handlers",
    "build_application",
    "configure_logging",
    "ensure_event_loop",
    "main",
]

logger = logging.getLogger(__name__)


def build_application() -> Application:
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Aborting.")
        sys.exit(1)

    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    add_handlers(app)
    register_summary_jobs(app)
    return app


def add_handlers(app: Application) -> None:
    """Register update handlers. Private chats only: in a group, every member
    would act as (and see the pipeline of) whoever linked that chat.
    Callback queries carry no message filter; handle_status_callback checks
    the chat type itself.
    """
    private = filters.ChatType.PRIVATE
    app.add_handler(CommandHandler("start", handle_start, filters=private))
    app.add_handler(CommandHandler("cancel", handle_cancel, filters=private))
    app.add_handler(CommandHandler("summary", handle_summary, filters=private))
    app.add_handler(CallbackQueryHandler(handle_status_callback, pattern=r"^status:"))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & private, handle_message)
    )


def ensure_event_loop() -> None:
    """PTB 21's run_polling calls asyncio.get_event_loop(), which raises on
    Python 3.14 when no loop is set (3.11 in Docker only warned). Set one."""
    asyncio.set_event_loop(asyncio.new_event_loop())


def main() -> None:
    configure_logging()
    ensure_event_loop()

    app = build_application()
    logger.info("Starting Telegram bot (long polling)...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
