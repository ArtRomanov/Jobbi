"""Stdlib logging setup for the long-running workers (Telegram bot, discovery)."""

import logging

__all__ = ["configure_logging"]


def configure_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    # httpx logs every request URL at INFO, and Bot API URLs embed the token
    # (https://api.telegram.org/bot<TOKEN>/...). Anyone reading the log could
    # drive the bot, so keep httpx to warnings and errors.
    logging.getLogger("httpx").setLevel(logging.WARNING)
