"""Discovery worker entry point. Run exactly one instance per deployment.

Run with: python -m app.discovery

Jobs (APScheduler 3.x `AsyncIOScheduler`):
- `run_initial_scans` every minute, and once right at start;
- `check_all` every hour;
- `cleanup` (retention) daily at 03:30 UTC (a cron time, so frequent restarts
  do not postpone it the way a 24 h interval would).
All are `max_instances=1, coalesce=True` and share one `asyncio.Lock`, so they
never run at the same time. On SIGINT/SIGTERM the scheduler stops and a running
job is cancelled; every step commits on its own, so nothing half-written is left.

Alerts go through a standalone `telegram.Bot` (no polling) when
`TELEGRAM_BOT_TOKEN` is set; without it, runs still mark cards as handled.
The token is never logged.
"""

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import groq
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot
from telegram.error import InvalidToken, TelegramError

from app.core.config import get_settings
from app.core.database import async_session
from app.core.telegram_send import describe_error
from app.core.worker_logging import configure_logging
from app.discovery.service import (
    DiscoveryConfig,
    check_all,
    cleanup,
    run_initial_scans,
)

__all__ = [
    "JobRunner",
    "build_scheduler",
    "close_bot",
    "main",
    "open_bot",
    "run_worker",
]

logger = logging.getLogger(__name__)

USER_AGENT = "Jobbi/1.0"
HTTP_TIMEOUT_S = 15.0
CHECK_INTERVAL_HOURS = 1
INITIAL_SCAN_INTERVAL_MINUTES = 1
CLEANUP_HOUR_UTC = 3
CLEANUP_MINUTE_UTC = 30
# A job that missed its time (e.g. while the other one held the lock) still
# runs if it is at most this late; coalesce folds repeated misses into one run.
MISFIRE_GRACE_S = 15 * 60


def utcnow() -> datetime:
    """Naive UTC, as stored in the database."""
    return datetime.now(UTC).replace(tzinfo=None)


class JobRunner:
    """Runs jobs one at a time under a shared lock and tracks the running task
    so shutdown can cancel it."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[Any]] = set()

    async def run(self, name: str, job: Callable[[], Awaitable[object]]) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        try:
            async with self.lock:
                await job()
        except asyncio.CancelledError:
            logger.info("Job %s cancelled", name)
            raise
        except Exception:  # keep the worker alive; the next run retries
            logger.exception("Job %s failed", name)
        finally:
            if task is not None:
                self._tasks.discard(task)

    async def cancel_running(self) -> None:
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def open_bot(token: str) -> Bot | None:
    """A ready `telegram.Bot` for alerts, or None when alerts are off.

    A rejected token disables alerts. If Telegram cannot be reached at start,
    the bot is still returned: `send_message` works without `initialize()`,
    so alerts resume once Telegram is reachable.
    """
    if not token:
        logger.info("TELEGRAM_BOT_TOKEN is not set: Telegram alerts are off")
        return None
    bot = Bot(token)
    try:
        await bot.initialize()
    except InvalidToken:
        # The exception text contains the token: do not log it.
        logger.error("Telegram rejected the bot token: Telegram alerts are off")
        return None
    except TelegramError as exc:
        logger.warning(
            "Could not reach Telegram at start (%s); alerts will still be tried",
            describe_error(exc, bot),
        )
    return bot


async def close_bot(bot: Bot | None) -> None:
    if bot is None:
        return
    try:
        await bot.shutdown()
    except TelegramError as exc:
        logger.warning("Telegram bot shutdown failed: %s", describe_error(exc, bot))


def build_scheduler(
    runner: JobRunner,
    http_client: httpx.AsyncClient,
    groq_client: groq.AsyncGroq,
    config: DiscoveryConfig,
    bot: Bot | None = None,
) -> AsyncIOScheduler:
    async def initial_scans_job() -> None:
        await runner.run(
            "run_initial_scans",
            lambda: run_initial_scans(
                async_session, http_client, groq_client, utcnow, config=config, bot=bot
            ),
        )

    async def check_all_job() -> None:
        await runner.run(
            "check_all",
            lambda: check_all(
                async_session, http_client, groq_client, utcnow, config=config, bot=bot
            ),
        )

    async def cleanup_job() -> None:
        await runner.run("cleanup", lambda: cleanup(async_session, utcnow))

    scheduler = AsyncIOScheduler(timezone=UTC)
    common = {
        "max_instances": 1,
        "coalesce": True,
        "misfire_grace_time": MISFIRE_GRACE_S,
    }
    scheduler.add_job(
        initial_scans_job,
        IntervalTrigger(minutes=INITIAL_SCAN_INTERVAL_MINUTES, timezone=UTC),
        id="run_initial_scans",
        # Also once right at start.
        next_run_time=datetime.now(UTC),
        **common,
    )
    scheduler.add_job(
        check_all_job,
        IntervalTrigger(hours=CHECK_INTERVAL_HOURS, timezone=UTC),
        id="check_all",
        **common,
    )
    scheduler.add_job(
        cleanup_job,
        CronTrigger(hour=CLEANUP_HOUR_UTC, minute=CLEANUP_MINUTE_UTC, timezone=UTC),
        id="cleanup",
        **common,
    )
    return scheduler


async def run_worker(stop: asyncio.Event | None = None) -> None:
    """Run until `stop` is set (or SIGINT/SIGTERM when `stop` is not given)."""
    settings = get_settings()
    config = DiscoveryConfig.from_settings(settings)
    if stop is None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)

    runner = JobRunner()
    bot = await open_bot(settings.TELEGRAM_BOT_TOKEN)
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT_S
    ) as http_client:
        groq_client = groq.AsyncGroq(api_key=settings.GROQ_API_KEY)
        scheduler = build_scheduler(runner, http_client, groq_client, config, bot)
        scheduler.start()
        logger.info(
            "Discovery worker started (model %s, daily limit %d, alerts %s)",
            config.model,
            config.daily_limit,
            "on" if bot is not None else "off",
        )
        try:
            await stop.wait()
        finally:
            logger.info("Discovery worker stopping...")
            scheduler.shutdown(wait=False)
            await runner.cancel_running()
            await groq_client.close()
            await close_bot(bot)
    logger.info("Discovery worker stopped")


def main() -> None:
    configure_logging()
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
