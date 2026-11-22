"""Discovery worker entry point. Run exactly one instance per deployment.

Run with: python -m app.discovery

Jobs (APScheduler 3.x `AsyncIOScheduler`):
- `run_initial_scans` every minute, and once right at start;
- `check_all` every hour.
Both are `max_instances=1, coalesce=True` and share one `asyncio.Lock`, so they
never run at the same time. On SIGINT/SIGTERM the scheduler stops and a running
job is cancelled; every step commits on its own, so nothing half-written is left.
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
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import get_settings
from app.core.database import async_session
from app.core.worker_logging import configure_logging
from app.discovery.service import DiscoveryConfig, check_all, run_initial_scans

__all__ = ["JobRunner", "build_scheduler", "main", "run_worker"]

logger = logging.getLogger(__name__)

USER_AGENT = "Jobbi/1.0"
HTTP_TIMEOUT_S = 15.0
CHECK_INTERVAL_HOURS = 1
INITIAL_SCAN_INTERVAL_MINUTES = 1
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


def build_scheduler(
    runner: JobRunner,
    http_client: httpx.AsyncClient,
    groq_client: groq.AsyncGroq,
    config: DiscoveryConfig,
) -> AsyncIOScheduler:
    async def initial_scans_job() -> None:
        await runner.run(
            "run_initial_scans",
            lambda: run_initial_scans(
                async_session, http_client, groq_client, utcnow, config=config
            ),
        )

    async def check_all_job() -> None:
        await runner.run(
            "check_all",
            lambda: check_all(
                async_session, http_client, groq_client, utcnow, config=config
            ),
        )

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
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT_S
    ) as http_client:
        groq_client = groq.AsyncGroq(api_key=settings.GROQ_API_KEY)
        scheduler = build_scheduler(runner, http_client, groq_client, config)
        scheduler.start()
        logger.info(
            "Discovery worker started (model %s, daily limit %d)",
            config.model,
            config.daily_limit,
        )
        try:
            await stop.wait()
        finally:
            logger.info("Discovery worker stopping...")
            scheduler.shutdown(wait=False)
            await runner.cancel_running()
            await groq_client.close()
    logger.info("Discovery worker stopped")


def main() -> None:
    configure_logging()
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
