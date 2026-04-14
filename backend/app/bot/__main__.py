"""Bot entry point: starts long polling for Telegram updates.

Run with: python -m app.bot
"""

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
from app.bot.handlers.start import handle_start
from app.core.config import get_settings

logger = logging.getLogger(__name__)


def build_application() -> Application:
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Aborting.")
        sys.exit(1)

    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("cancel", handle_cancel))
    app.add_handler(CallbackQueryHandler(handle_status_callback, pattern=r"^status:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    app = build_application()
    logger.info("Starting Telegram bot (long polling)...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
