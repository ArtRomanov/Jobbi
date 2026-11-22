import asyncio
import logging
from typing import Any

import httpx
import pytest
from telegram import Bot
from telegram.error import InvalidToken, NetworkError

from app.discovery import __main__ as worker
from app.discovery.service import DiscoveryConfig

CONFIG = DiscoveryConfig(model="m", daily_limit=1)


async def test_jobs_never_overlap() -> None:
    runner = worker.JobRunner()
    events: list[str] = []

    def job(name: str) -> Any:
        async def run() -> None:
            events.append(f"{name} start")
            await asyncio.sleep(0.01)
            events.append(f"{name} end")

        return run

    await asyncio.gather(runner.run("a", job("a")), runner.run("b", job("b")))

    assert events == ["a start", "a end", "b start", "b end"]


async def test_failing_job_is_logged_and_lock_released(caplog) -> None:
    runner = worker.JobRunner()

    async def boom() -> None:
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR):
        await runner.run("boom", boom)

    assert "Job boom failed" in caplog.text
    assert not runner.lock.locked()


async def test_cancel_running_stops_a_job() -> None:
    runner = worker.JobRunner()
    started = asyncio.Event()

    async def forever() -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(runner.run("forever", forever))
    await started.wait()
    await runner.cancel_running()

    assert task.cancelled()
    assert not runner.lock.locked()


async def test_scheduler_jobs() -> None:
    async with httpx.AsyncClient() as http:
        scheduler = worker.build_scheduler(worker.JobRunner(), http, object(), CONFIG)  # type: ignore[arg-type]

    jobs = {job.id: job for job in scheduler.get_jobs()}
    assert set(jobs) == {"run_initial_scans", "check_all", "cleanup"}
    for job in jobs.values():
        assert job.max_instances == 1
        assert job.coalesce is True
    assert jobs["check_all"].trigger.interval.total_seconds() == 3600
    assert jobs["run_initial_scans"].trigger.interval.total_seconds() == 60
    # Daily at a fixed UTC time (restarts do not postpone it).
    cleanup_fields = {f.name: str(f) for f in jobs["cleanup"].trigger.fields}
    assert (cleanup_fields["hour"], cleanup_fields["minute"]) == ("3", "30")
    assert cleanup_fields["day"] == "*"


async def test_cleanup_job_runs_under_the_shared_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = worker.JobRunner()
    seen_locked: list[bool] = []

    async def fake_cleanup(*args: Any, **kwargs: Any) -> None:
        seen_locked.append(runner.lock.locked())

    monkeypatch.setattr(worker, "cleanup", fake_cleanup)
    async with httpx.AsyncClient() as http:
        scheduler = worker.build_scheduler(runner, http, object(), CONFIG)  # type: ignore[arg-type]
        await scheduler.get_job("cleanup").func()

    assert seen_locked == [True]


async def test_run_worker_scans_at_start_and_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    scanned = asyncio.Event()

    async def fake_initial(*args: Any, **kwargs: Any) -> None:
        calls.append("initial")
        scanned.set()

    async def fake_check(*args: Any, **kwargs: Any) -> None:  # pragma: no cover
        calls.append("check")

    async def no_bot(token: str) -> None:
        return None

    monkeypatch.setattr(worker, "open_bot", no_bot)
    monkeypatch.setattr(worker, "run_initial_scans", fake_initial)
    monkeypatch.setattr(worker, "check_all", fake_check)
    stop = asyncio.Event()

    task = asyncio.create_task(worker.run_worker(stop))
    await asyncio.wait_for(scanned.wait(), timeout=5)
    stop.set()
    await asyncio.wait_for(task, timeout=5)

    assert calls == ["initial"]


# --- Telegram bot for alerts ----------------------------------------------------

TOKEN = "123456:SECRET-TOKEN"


async def test_open_bot_without_token_disables_alerts() -> None:
    assert await worker.open_bot("") is None


async def test_open_bot_initializes_and_close_shuts_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def initialize(self: Bot) -> None:
        calls.append("initialize")

    async def shutdown(self: Bot) -> None:
        calls.append("shutdown")

    monkeypatch.setattr(Bot, "initialize", initialize)
    monkeypatch.setattr(Bot, "shutdown", shutdown)

    bot = await worker.open_bot(TOKEN)
    assert isinstance(bot, Bot)
    await worker.close_bot(bot)
    await worker.close_bot(None)

    assert calls == ["initialize", "shutdown"]


async def test_open_bot_rejected_token_disables_alerts_without_logging_it(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def initialize(self: Bot) -> None:
        raise InvalidToken(f"The token `{TOKEN}` was rejected by the server.")

    monkeypatch.setattr(Bot, "initialize", initialize)

    # INFO as in the worker (PTB itself logs the token at DEBUG).
    with caplog.at_level(logging.INFO):
        assert await worker.open_bot(TOKEN) is None

    assert "rejected the bot token" in caplog.text
    assert TOKEN not in caplog.text


async def test_open_bot_unreachable_telegram_keeps_the_bot(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def initialize(self: Bot) -> None:
        raise NetworkError(f"https://api.telegram.org/bot{TOKEN}/getMe unreachable")

    monkeypatch.setattr(Bot, "initialize", initialize)

    # INFO as in the worker (PTB itself logs the token at DEBUG).
    with caplog.at_level(logging.INFO):
        bot = await worker.open_bot(TOKEN)

    assert isinstance(bot, Bot)
    assert "Could not reach Telegram" in caplog.text
    assert TOKEN not in caplog.text
