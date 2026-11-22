import asyncio
import logging
from typing import Any

import httpx
import pytest

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
    assert set(jobs) == {"run_initial_scans", "check_all"}
    for job in jobs.values():
        assert job.max_instances == 1
        assert job.coalesce is True
    assert jobs["check_all"].trigger.interval.total_seconds() == 3600
    assert jobs["run_initial_scans"].trigger.interval.total_seconds() == 60


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

    monkeypatch.setattr(worker, "run_initial_scans", fake_initial)
    monkeypatch.setattr(worker, "check_all", fake_check)
    stop = asyncio.Event()

    task = asyncio.create_task(worker.run_worker(stop))
    await asyncio.wait_for(scanned.wait(), timeout=5)
    stop.set()
    await asyncio.wait_for(task, timeout=5)

    assert calls == ["initial"]
