"""JobQueue setup for daily pipeline summaries.

One daily job per linked user, named `daily_summary:<user_id>`. A sync job
runs on startup and every 5 minutes, diffing the registered jobs against the
database (new links, changed time/timezone, disconnects). Because job names
are stable and each job carries the schedule it was built from, the sync is
idempotent: unchanged jobs are left alone, changed ones are replaced.

The daily job sends at most one summary per user per local calendar day
(tracked in memory in `application.bot_data`), so a DST fall-back hour or a
summary_time moved later the same day cannot produce a second message.
/summary on demand is not affected.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from telegram.error import Forbidden, RetryAfter, TelegramError
from telegram.ext import Application, ContextTypes, JobQueue

from app.core.database import async_session
from app.core.timezones import is_valid_timezone
from app.models.telegram_link import TelegramLink
from app.models.user import User
from app.services.summary_service import build_summary
from app.services.telegram_service import get_user_link

logger = logging.getLogger(__name__)

SUMMARY_JOB_PREFIX = "daily_summary:"
SYNC_JOB_NAME = "summary_sync"
INITIAL_SYNC_JOB_NAME = "summary_sync_initial"
SYNC_INTERVAL_SECONDS = 5 * 60
# APScheduler's default misfire grace is 1s: a briefly busy event loop would
# silently skip that day's summary. Late by up to 15 minutes still sends.
DAILY_MISFIRE_GRACE_SECONDS = 15 * 60
LAST_SENT_KEY = "summary_last_sent_local_date"
DEFAULT_SUMMARY_TIME = "10:00"
DEFAULT_TIMEZONE = "UTC"


@dataclass(frozen=True, slots=True)
class SummarySchedule:
    """What a user's daily job was built from; compared on every sync."""

    user_id: str
    chat_id: int
    summary_time: str
    timezone: str

    @property
    def job_name(self) -> str:
        return summary_job_name(self.user_id)


def summary_job_name(user_id: str) -> str:
    return f"{SUMMARY_JOB_PREFIX}{user_id}"


def _now_utc() -> datetime:
    return datetime.now(UTC)


# Indirection so tests can skip the real wait.
_sleep = asyncio.sleep


def _resolve_timezone(name: str | None, user_id: str) -> str:
    if not name:
        return DEFAULT_TIMEZONE
    if not is_valid_timezone(name):
        logger.warning(
            "Unknown timezone %r for user %s; falling back to UTC", name, user_id
        )
        return DEFAULT_TIMEZONE
    return name


def _resolve_summary_time(value: str | None, user_id: str) -> str:
    try:
        hour_str, minute_str = (value or "").split(":")
        parsed = time(int(hour_str), int(minute_str))
    except ValueError:
        logger.warning(
            "Invalid summary_time %r for user %s; falling back to %s",
            value,
            user_id,
            DEFAULT_SUMMARY_TIME,
        )
        return DEFAULT_SUMMARY_TIME
    return parsed.strftime("%H:%M")


def _to_run_time(schedule: SummarySchedule) -> time:
    hour, minute = (int(part) for part in schedule.summary_time.split(":"))
    return time(hour, minute, tzinfo=ZoneInfo(schedule.timezone))


async def load_schedules() -> dict[str, SummarySchedule]:
    """Return the desired schedule for every linked user, keyed by job name."""
    async with async_session() as db:
        result = await db.execute(
            select(
                TelegramLink.user_id,
                TelegramLink.chat_id,
                User.summary_time,
                User.timezone,
            ).join(User, User.id == TelegramLink.user_id)
        )
        rows = result.all()

    schedules = (
        SummarySchedule(
            user_id=user_id,
            chat_id=chat_id,
            summary_time=_resolve_summary_time(summary_time, user_id),
            timezone=_resolve_timezone(tz_name, user_id),
        )
        for user_id, chat_id, summary_time, tz_name in rows
    )
    return {schedule.job_name: schedule for schedule in schedules}


def apply_schedules(
    job_queue: JobQueue, desired: dict[str, SummarySchedule]
) -> None:
    """Make the registered summary jobs match `desired` exactly."""
    existing = {
        job.name: job
        for job in job_queue.jobs()
        if job.name and job.name.startswith(SUMMARY_JOB_PREFIX)
    }

    for name, job in existing.items():
        if desired.get(name) != job.data:
            job.schedule_removal()
            logger.info("Removed daily summary job %s", name)

    for name, schedule in desired.items():
        current = existing.get(name)
        if current is not None and current.data == schedule:
            continue
        try:
            job_queue.run_daily(
                send_daily_summary,
                time=_to_run_time(schedule),
                name=name,
                data=schedule,
                chat_id=schedule.chat_id,
                job_kwargs={
                    "misfire_grace_time": DAILY_MISFIRE_GRACE_SECONDS,
                    "coalesce": True,
                },
            )
        except Exception:
            # One user's bad data must not stop everyone else's summaries.
            logger.exception("Failed to schedule daily summary job %s", name)
            continue
        logger.info(
            "Scheduled daily summary job %s at %s %s",
            name,
            schedule.summary_time,
            schedule.timezone,
        )


async def sync_summary_jobs(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodic job: reconcile per-user summary jobs with the database."""
    if context.job_queue is None:
        return
    try:
        desired = await load_schedules()
    except SQLAlchemyError:
        logger.exception("Failed to load summary schedules; keeping current jobs")
        return
    except Exception:
        logger.exception("Failed to sync summary jobs; keeping current jobs")
        return
    try:
        apply_schedules(context.job_queue, desired)
    except Exception:
        logger.exception("Failed to sync summary jobs; keeping current jobs")


def _local_today(schedule: SummarySchedule) -> date:
    return _now_utc().astimezone(ZoneInfo(schedule.timezone)).date()


async def _send_with_retry(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str
) -> None:
    """Send once; on flood control wait the requested time and retry once."""
    try:
        await context.bot.send_message(chat_id=chat_id, text=text)
    except RetryAfter as exc:
        delay = exc.retry_after
        seconds = delay.total_seconds() if isinstance(delay, timedelta) else delay
        logger.warning("Flood control: retrying summary in %ss", seconds)
        await _sleep(seconds)
        await context.bot.send_message(chat_id=chat_id, text=text)


async def send_daily_summary(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Daily job: build and send one user's summary.

    Failures are logged and swallowed so one bad chat never affects others.
    """
    job = context.job
    if job is None or not isinstance(job.data, SummarySchedule):
        return
    schedule = job.data
    last_sent: dict[str, date] = context.bot_data.setdefault(LAST_SENT_KEY, {})
    today = _local_today(schedule)
    if last_sent.get(schedule.user_id) == today:
        logger.info(
            "Skipping summary for user %s: already sent on %s",
            schedule.user_id,
            today,
        )
        return

    try:
        async with async_session() as db:
            # Re-check the link: the user may have disconnected since the last sync.
            link = await get_user_link(db, schedule.user_id)
            if link is None or link.chat_id != schedule.chat_id:
                logger.info(
                    "Skipping summary for user %s: link removed or changed",
                    schedule.user_id,
                )
                return
            text = await build_summary(db, schedule.user_id)
        await _send_with_retry(context, schedule.chat_id, text)
        last_sent[schedule.user_id] = today
    except Forbidden:
        logger.warning(
            "Cannot send summary to user %s: bot blocked or chat unavailable",
            schedule.user_id,
        )
    except TelegramError:
        logger.exception("Telegram error sending summary to user %s", schedule.user_id)
    except SQLAlchemyError:
        logger.exception("Database error building summary for user %s", schedule.user_id)


def register_summary_jobs(app: Application) -> None:
    """Schedule the summary sync: once as soon as the queue starts, then every
    SYNC_INTERVAL_SECONDS.

    A separate one-shot job is needed for the startup run: run_repeating's
    `first` is resolved when this is called, and if the queue starts later than
    that (it does, after getMe/deleteWebhook), APScheduler's interval trigger
    skips the past start and the first sync would only run after a full
    interval. A one-shot job with no misfire limit runs on start however late.
    """
    if app.job_queue is None:
        logger.error(
            "JobQueue unavailable (install python-telegram-bot[job-queue]); "
            "daily summaries are disabled."
        )
        return
    app.job_queue.run_once(
        sync_summary_jobs,
        when=0,
        name=INITIAL_SYNC_JOB_NAME,
        job_kwargs={"misfire_grace_time": None},
    )
    app.job_queue.run_repeating(
        sync_summary_jobs,
        interval=SYNC_INTERVAL_SECONDS,
        first=SYNC_INTERVAL_SECONDS,
        name=SYNC_JOB_NAME,
    )
