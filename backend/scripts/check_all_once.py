"""Run the discovery worker's hourly check once, right now.

Reads every source, rates new posts with Groq and sends bot alerts, exactly as
the worker's hourly job does, then prints the run report. Use it to sync
without waiting for the next hour (e.g. after the Mac slept). It works on the
database DATABASE_URL points to and spends real Groq quota.

Usage (from backend/; keys are never printed):
    set -a; . ../.env; set +a; .venv/bin/python scripts/check_all_once.py
Env: the same as the worker (DATABASE_URL, GROQ_API_KEY, TELEGRAM_BOT_TOKEN,
DISCOVERY_* settings).

The worker's in-process lock does not cover this script: avoid starting it
in the minutes around the worker's own hourly check.
"""

import asyncio
import logging

import groq
import httpx

from app.core.config import get_settings
from app.core.database import async_session
from app.core.worker_logging import configure_logging
from app.discovery import __main__ as worker
from app.discovery.service import DiscoveryConfig, check_all


async def run() -> None:
    settings = get_settings()
    config = DiscoveryConfig.from_settings(settings)
    bot = await worker.open_bot(settings.TELEGRAM_BOT_TOKEN)
    async with httpx.AsyncClient(
        headers={"User-Agent": worker.USER_AGENT}, timeout=worker.HTTP_TIMEOUT_S
    ) as http_client:
        groq_client = groq.AsyncGroq(api_key=settings.GROQ_API_KEY)
        try:
            report = await check_all(
                async_session,
                http_client,
                groq_client,
                worker.utcnow,
                config=config,
                bot=bot,
            )
            logging.getLogger("check_all_once").info("done: %s", report)
        finally:
            await groq_client.close()
            await worker.close_bot(bot)


if __name__ == "__main__":
    configure_logging()
    asyncio.run(run())
