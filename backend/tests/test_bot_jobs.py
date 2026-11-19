"""Tests for the daily-summary JobQueue wiring in app.bot.handlers.jobs.

Scheduling tests use a real python-telegram-bot JobQueue (backed by APScheduler)
so job names, run times and replacement semantics are checked against the
library rather than a mock. No network access is needed: the queue never talks
to Telegram.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import TypeAlias
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from telegram.error import Forbidden, NetworkError, TelegramError
from telegram.ext import Application, ApplicationBuilder, JobQueue

from app.bot.handlers import jobs
from app.bot.handlers.jobs import (
    SYNC_INTERVAL_SECONDS,
    SYNC_JOB_NAME,
    SummarySchedule,
    apply_schedules,
    load_schedules,
    register_summary_jobs,
    send_daily_summary,
    summary_job_name,
    sync_summary_jobs,
)
from app.models.telegram_link import TelegramLink
from app.models.user import User
from app.services.summary_service import EMPTY_STATE_MESSAGE
from tests.conftest import TestSessionLocal

CHAT_ID = 777_000_111
OTHER_CHAT_ID = 777_000_222
FAKE_TOKEN = "123:fake"

MakeUser: TypeAlias = Callable[..., Awaitable[User]]


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _use_test_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the module's session factory at the in-memory test DB."""
    monkeypatch.setattr(jobs, "async_session", TestSessionLocal)


@pytest.fixture
def app() -> Application:
    """A PTB application with a real (not yet started) JobQueue."""
    return ApplicationBuilder().token(FAKE_TOKEN).build()


@pytest.fixture
async def job_queue(app: Application) -> AsyncGenerator[JobQueue, None]:
    """A started real JobQueue, stopped after the test."""
    assert app.job_queue is not None
    await app.job_queue.start()
    yield app.job_queue
    await app.job_queue.stop()


@pytest.fixture
async def linked_user(db_session: AsyncSession, make_user: MakeUser) -> User:
    user = await make_user()
    db_session.add(TelegramLink(user_id=user.id, chat_id=CHAT_ID))
    await db_session.commit()
    return user


def _schedule(
    user_id: str = "user-1",
    *,
    chat_id: int = CHAT_ID,
    summary_time: str = "10:00",
    timezone: str = "UTC",
) -> SummarySchedule:
    return SummarySchedule(
        user_id=user_id, chat_id=chat_id, summary_time=summary_time, timezone=timezone
    )


def _kwargs(schedule: SummarySchedule) -> dict[str, object]:
    return {
        "chat_id": schedule.chat_id,
        "summary_time": schedule.summary_time,
        "timezone": schedule.timezone,
    }


def _desired(*schedules: SummarySchedule) -> dict[str, SummarySchedule]:
    return {s.job_name: s for s in schedules}


def _summary_jobs(job_queue: JobQueue) -> dict[str, object]:
    """Registered summary jobs keyed by name -> underlying APScheduler job id."""
    return {
        job.name: job.job.id
        for job in job_queue.jobs()
        if job.name and job.name.startswith(jobs.SUMMARY_JOB_PREFIX)
    }


class FakeBot:
    """Records send_message calls; optionally raises a preset error."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.sent: list[dict[str, object]] = []

    async def send_message(self, *, chat_id: int, text: str) -> None:
        if self.error is not None:
            raise self.error
        self.sent.append({"chat_id": chat_id, "text": text})


def _job_context(data: object, bot: FakeBot) -> SimpleNamespace:
    return SimpleNamespace(job=SimpleNamespace(data=data), bot=bot)


# ---------------------------------------------------------------------------
# load_schedules
# ---------------------------------------------------------------------------


async def test_load_schedules_returns_only_linked_users(
    db_session: AsyncSession, make_user: MakeUser
) -> None:
    linked = await make_user(summary_time="08:15", timezone="Europe/Berlin")
    await make_user()  # never linked
    db_session.add(TelegramLink(user_id=linked.id, chat_id=CHAT_ID))
    await db_session.commit()

    schedules = await load_schedules()

    assert schedules == {
        summary_job_name(linked.id): SummarySchedule(
            user_id=linked.id,
            chat_id=CHAT_ID,
            summary_time="08:15",
            timezone="Europe/Berlin",
        )
    }


async def test_load_schedules_empty_when_nobody_linked(make_user: MakeUser) -> None:
    await make_user()

    assert await load_schedules() == {}


async def test_load_schedules_null_timezone_defaults_to_utc(
    linked_user: User,
) -> None:
    assert linked_user.timezone is None

    schedules = await load_schedules()

    assert schedules[summary_job_name(linked_user.id)].timezone == "UTC"


@pytest.mark.parametrize(
    "bad_timezone",
    ["Mars/Olympus_Mons", "", "../../etc/passwd", "/etc/localtime", "zone.tab"],
)
async def test_load_schedules_invalid_timezone_falls_back_to_utc(
    db_session: AsyncSession,
    linked_user: User,
    bad_timezone: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Written straight to the row, bypassing the API's timezone validation.
    await db_session.execute(
        update(User).where(User.id == linked_user.id).values(timezone=bad_timezone)
    )
    await db_session.commit()

    with caplog.at_level(logging.WARNING, logger=jobs.__name__):
        schedules = await load_schedules()

    assert schedules[summary_job_name(linked_user.id)].timezone == "UTC"
    if bad_timezone:  # empty string is treated like NULL, no warning
        assert "Unknown timezone" in caplog.text


@pytest.mark.parametrize(
    "bad_time", ["25:00", "10:60", "garbage", "1000", "10:00:00", "", "-1:30"]
)
async def test_load_schedules_invalid_summary_time_falls_back_to_default(
    db_session: AsyncSession,
    linked_user: User,
    bad_time: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await db_session.execute(
        update(User).where(User.id == linked_user.id).values(summary_time=bad_time)
    )
    await db_session.commit()

    with caplog.at_level(logging.WARNING, logger=jobs.__name__):
        schedules = await load_schedules()

    assert schedules[summary_job_name(linked_user.id)].summary_time == "10:00"
    assert "Invalid summary_time" in caplog.text


async def test_load_schedules_normalizes_unpadded_time(
    db_session: AsyncSession, linked_user: User
) -> None:
    await db_session.execute(
        update(User).where(User.id == linked_user.id).values(summary_time="7:5")
    )
    await db_session.commit()

    schedules = await load_schedules()

    assert schedules[summary_job_name(linked_user.id)].summary_time == "07:05"


# ---------------------------------------------------------------------------
# apply_schedules
# ---------------------------------------------------------------------------


async def test_apply_creates_one_named_job_per_user(job_queue: JobQueue) -> None:
    alice = _schedule(
        "alice", chat_id=CHAT_ID, summary_time="09:30", timezone="Asia/Tokyo"
    )
    bob = _schedule(
        "bob", chat_id=OTHER_CHAT_ID, summary_time="18:45", timezone="America/New_York"
    )

    apply_schedules(job_queue, _desired(alice, bob))

    registered = {job.name: job for job in job_queue.jobs()}
    assert set(registered) == {"daily_summary:alice", "daily_summary:bob"}
    for schedule in (alice, bob):
        job = registered[schedule.job_name]
        assert job.data == schedule
        assert job.chat_id == schedule.chat_id
        assert job.callback is send_daily_summary
        local_next = job.next_t.astimezone(ZoneInfo(schedule.timezone))
        assert local_next.strftime("%H:%M") == schedule.summary_time
        assert local_next > datetime.now(UTC)
        assert local_next - datetime.now(UTC) <= timedelta(days=1)


async def test_apply_same_state_is_idempotent(job_queue: JobQueue) -> None:
    desired = _desired(_schedule("alice"), _schedule("bob", chat_id=OTHER_CHAT_ID))
    apply_schedules(job_queue, desired)
    first_ids = _summary_jobs(job_queue)

    apply_schedules(job_queue, dict(desired))
    apply_schedules(job_queue, dict(desired))

    assert _summary_jobs(job_queue) == first_ids


@pytest.mark.parametrize(
    "changes",
    [
        {"summary_time": "11:30"},
        {"timezone": "Europe/Berlin"},
        {"chat_id": OTHER_CHAT_ID},
    ],
    ids=["time", "timezone", "chat_id"],
)
async def test_apply_changed_schedule_replaces_job(
    job_queue: JobQueue, changes: dict[str, object]
) -> None:
    original = _schedule("alice")
    untouched = _schedule("bob", chat_id=999)
    apply_schedules(job_queue, _desired(original, untouched))
    before = _summary_jobs(job_queue)
    changed = _schedule("alice", **{**_kwargs(original), **changes})

    apply_schedules(job_queue, _desired(changed, untouched))

    after = _summary_jobs(job_queue)
    assert set(after) == set(before)
    assert after["daily_summary:alice"] != before["daily_summary:alice"]
    assert after["daily_summary:bob"] == before["daily_summary:bob"]
    alice_jobs = [j for j in job_queue.jobs() if j.name == "daily_summary:alice"]
    assert len(alice_jobs) == 1
    assert alice_jobs[0].data == changed
    local_next = alice_jobs[0].next_t.astimezone(ZoneInfo(changed.timezone))
    assert local_next.strftime("%H:%M") == changed.summary_time


async def test_apply_removes_job_for_dropped_user(job_queue: JobQueue) -> None:
    alice, bob = _schedule("alice"), _schedule("bob", chat_id=OTHER_CHAT_ID)
    apply_schedules(job_queue, _desired(alice, bob))
    bob_id = _summary_jobs(job_queue)["daily_summary:bob"]

    apply_schedules(job_queue, _desired(bob))

    assert _summary_jobs(job_queue) == {"daily_summary:bob": bob_id}


async def test_apply_empty_desired_removes_all_summary_jobs(
    job_queue: JobQueue,
) -> None:
    apply_schedules(
        job_queue, _desired(_schedule("alice"), _schedule("bob", chat_id=2))
    )

    apply_schedules(job_queue, {})

    assert _summary_jobs(job_queue) == {}


async def test_apply_never_touches_non_summary_jobs(job_queue: JobQueue) -> None:
    async def _noop(_: object) -> None:
        return None

    sync_job = job_queue.run_repeating(
        _noop, interval=3600, first=3600, name=SYNC_JOB_NAME
    )
    unnamed_job = job_queue.run_repeating(_noop, interval=3600, first=3600)
    keep_ids = {sync_job.job.id, unnamed_job.job.id}

    apply_schedules(job_queue, _desired(_schedule("alice")))
    apply_schedules(job_queue, {})

    remaining = {job.job.id for job in job_queue.jobs()}
    assert remaining == keep_ids


# ---------------------------------------------------------------------------
# sync_summary_jobs
# ---------------------------------------------------------------------------


async def test_sync_registers_jobs_from_database(
    job_queue: JobQueue, linked_user: User
) -> None:
    await sync_summary_jobs(SimpleNamespace(job_queue=job_queue))

    assert set(_summary_jobs(job_queue)) == {summary_job_name(linked_user.id)}


async def test_sync_removes_job_after_disconnect(
    job_queue: JobQueue, db_session: AsyncSession, linked_user: User
) -> None:
    context = SimpleNamespace(job_queue=job_queue)
    await sync_summary_jobs(context)
    await db_session.execute(
        delete(TelegramLink).where(TelegramLink.user_id == linked_user.id)
    )
    await db_session.commit()

    await sync_summary_jobs(context)

    assert _summary_jobs(job_queue) == {}


async def test_sync_db_error_keeps_existing_jobs(
    job_queue: JobQueue,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    apply_schedules(
        job_queue, _desired(_schedule("alice"), _schedule("bob", chat_id=2))
    )
    before = _summary_jobs(job_queue)

    async def _failing_load() -> dict[str, SummarySchedule]:
        raise OperationalError("SELECT 1", {}, Exception("database is locked"))

    monkeypatch.setattr(jobs, "load_schedules", _failing_load)

    with caplog.at_level(logging.ERROR, logger=jobs.__name__):
        await sync_summary_jobs(SimpleNamespace(job_queue=job_queue))

    assert _summary_jobs(job_queue) == before
    assert "Failed to load summary schedules" in caplog.text


async def test_sync_without_job_queue_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[None] = []

    async def _tracking_load() -> dict[str, SummarySchedule]:
        calls.append(None)
        return {}

    monkeypatch.setattr(jobs, "load_schedules", _tracking_load)

    await sync_summary_jobs(SimpleNamespace(job_queue=None))

    assert calls == []


# ---------------------------------------------------------------------------
# send_daily_summary
# ---------------------------------------------------------------------------


async def test_send_daily_summary_sends_to_linked_chat(linked_user: User) -> None:
    bot = FakeBot()
    schedule = _schedule(linked_user.id, chat_id=CHAT_ID)

    await send_daily_summary(_job_context(schedule, bot))

    assert len(bot.sent) == 1
    assert bot.sent[0]["chat_id"] == CHAT_ID
    assert str(bot.sent[0]["text"]).startswith(EMPTY_STATE_MESSAGE)


async def test_send_daily_summary_uses_build_summary_text(
    linked_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen_user_ids: list[str] = []

    async def _fake_build_summary(_db: AsyncSession, user_id: str) -> str:
        seen_user_ids.append(user_id)
        return "your pipeline today"

    monkeypatch.setattr(jobs, "build_summary", _fake_build_summary)
    bot = FakeBot()

    await send_daily_summary(_job_context(_schedule(linked_user.id), bot))

    assert seen_user_ids == [linked_user.id]
    assert bot.sent == [{"chat_id": CHAT_ID, "text": "your pipeline today"}]


async def test_send_daily_summary_skips_when_link_removed(
    db_session: AsyncSession, linked_user: User, caplog: pytest.LogCaptureFixture
) -> None:
    await db_session.execute(
        delete(TelegramLink).where(TelegramLink.user_id == linked_user.id)
    )
    await db_session.commit()
    bot = FakeBot()

    with caplog.at_level(logging.INFO, logger=jobs.__name__):
        await send_daily_summary(_job_context(_schedule(linked_user.id), bot))

    assert bot.sent == []
    assert "link removed or changed" in caplog.text


async def test_send_daily_summary_skips_when_link_moved_to_other_chat(
    db_session: AsyncSession, linked_user: User
) -> None:
    await db_session.execute(
        update(TelegramLink)
        .where(TelegramLink.user_id == linked_user.id)
        .values(chat_id=OTHER_CHAT_ID)
    )
    await db_session.commit()
    bot = FakeBot()

    await send_daily_summary(
        _job_context(_schedule(linked_user.id, chat_id=CHAT_ID), bot)
    )

    assert bot.sent == []


@pytest.mark.parametrize(
    ("error", "level", "message"),
    [
        (
            Forbidden("bot was blocked by the user"),
            logging.WARNING,
            "Cannot send summary",
        ),
        (TelegramError("boom"), logging.ERROR, "Telegram error sending summary"),
        (
            NetworkError("connection reset"),
            logging.ERROR,
            "Telegram error sending summary",
        ),
    ],
    ids=["forbidden", "telegram-error", "network-error"],
)
async def test_send_daily_summary_swallows_telegram_errors(
    linked_user: User,
    caplog: pytest.LogCaptureFixture,
    error: TelegramError,
    level: int,
    message: str,
) -> None:
    bot = FakeBot(error=error)

    with caplog.at_level(logging.DEBUG, logger=jobs.__name__):
        await send_daily_summary(_job_context(_schedule(linked_user.id), bot))

    matching = [r for r in caplog.records if message in r.getMessage()]
    assert len(matching) == 1
    assert matching[0].levelno == level
    assert linked_user.id in matching[0].getMessage()


@pytest.mark.parametrize("failing_call", ["get_user_link", "build_summary"])
async def test_send_daily_summary_swallows_database_errors(
    linked_user: User,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failing_call: str,
) -> None:
    async def _raise(*_args: object, **_kwargs: object) -> None:
        raise SQLAlchemyError("connection lost")

    monkeypatch.setattr(jobs, failing_call, _raise)
    bot = FakeBot()

    with caplog.at_level(logging.ERROR, logger=jobs.__name__):
        await send_daily_summary(_job_context(_schedule(linked_user.id), bot))

    assert bot.sent == []
    assert "Database error building summary" in caplog.text


@pytest.mark.parametrize(
    "data",
    [None, "daily_summary:user-1", {"user_id": "user-1", "chat_id": CHAT_ID}],
    ids=["none", "string", "dict"],
)
async def test_send_daily_summary_ignores_unexpected_job_data(
    linked_user: User, data: object
) -> None:
    bot = FakeBot()

    await send_daily_summary(_job_context(data, bot))

    assert bot.sent == []


async def test_send_daily_summary_without_job_is_noop() -> None:
    bot = FakeBot()

    await send_daily_summary(SimpleNamespace(job=None, bot=bot))

    assert bot.sent == []


# ---------------------------------------------------------------------------
# register_summary_jobs
# ---------------------------------------------------------------------------


async def test_register_adds_repeating_sync_job(
    job_queue: JobQueue, app: Application
) -> None:
    register_summary_jobs(app)

    sync_jobs = [job for job in job_queue.jobs() if job.name == SYNC_JOB_NAME]
    assert len(sync_jobs) == 1
    sync_job = sync_jobs[0]
    assert sync_job.callback is sync_summary_jobs
    assert sync_job.job.trigger.interval == timedelta(seconds=SYNC_INTERVAL_SECONDS)
    assert SYNC_INTERVAL_SECONDS == 300


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "first=0 is resolved to 'now' when run_repeating is called; by the time "
        "APScheduler computes the first fire time 'now' has moved on, so the "
        "IntervalTrigger skips to start+interval. The sync (and therefore every "
        "daily job) first runs ~5 minutes after startup, not immediately as "
        "register_summary_jobs' docstring promises (jobs.py:191, 201)."
    ),
)
async def test_register_first_sync_runs_immediately_on_startup(
    app: Application,
) -> None:
    # Production order (app/bot/__main__.py): register first, start the queue later.
    register_summary_jobs(app)
    assert app.job_queue is not None
    await asyncio.sleep(0.05)
    await app.job_queue.start()
    try:
        (sync_job,) = [j for j in app.job_queue.jobs() if j.name == SYNC_JOB_NAME]
        assert sync_job.next_t - datetime.now(UTC) <= timedelta(seconds=5)
    finally:
        await app.job_queue.stop()


@pytest.mark.filterwarnings("ignore::telegram.warnings.PTBUserWarning")
async def test_register_without_job_queue_logs_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app_without_queue = ApplicationBuilder().token(FAKE_TOKEN).job_queue(None).build()
    assert app_without_queue.job_queue is None

    with caplog.at_level(logging.ERROR, logger=jobs.__name__):
        register_summary_jobs(app_without_queue)

    assert "JobQueue unavailable" in caplog.text
    assert any(r.levelno == logging.ERROR for r in caplog.records)
