"""Build the pipeline summary text sent by the Telegram bot.

Shared by the `/summary` command, the daily JobQueue job, and any future API
endpoint. Uses only portable SQLAlchemy constructs (GROUP BY, COALESCE, outer
join on an aggregate subquery) so it runs unchanged on SQLite and PostgreSQL.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import ApplicationStatus
from app.models.application import Application, ApplicationStatusHistory
from app.services.vacancy_service import count_new

RECENT_ACTIVITY_WINDOW = timedelta(hours=24)
FOLLOW_UP_AFTER = timedelta(days=7)

EMPTY_STATE_MESSAGE = "📭 No applications tracked yet. Add one to get started!"
SUMMARY_HEADER = "📋 Your Jobbi summary"


def _to_naive_utc(moment: datetime) -> datetime:
    """Timestamps are stored as naive UTC; normalize `now` to match."""
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    word = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {word}"


async def _count_by_status(db: AsyncSession, user_id: str) -> dict[str, int]:
    result = await db.execute(
        select(Application.status, func.count(Application.id))
        .where(Application.user_id == user_id)
        .group_by(Application.status)
    )
    return {status: count for status, count in result.all()}


async def _count_recent_status_changes(
    db: AsyncSession, user_id: str, since: datetime
) -> int:
    """Count status-history entries in the window.

    Includes the initial entry written when an application is created, so a
    newly added application counts as activity.
    """
    result = await db.execute(
        select(func.count(ApplicationStatusHistory.id))
        .join(Application, ApplicationStatusHistory.application_id == Application.id)
        .where(
            Application.user_id == user_id,
            ApplicationStatusHistory.changed_at >= since,
        )
    )
    return result.scalar_one()


async def _count_follow_ups(db: AsyncSession, user_id: str, cutoff: datetime) -> int:
    """Count applications currently Applied that entered Applied before `cutoff`.

    "Entered Applied" = the latest status-history row with status `applied`;
    falls back to `created_at` when no such history row exists.
    """
    applied = ApplicationStatus.APPLIED.value
    entered_applied = (
        select(
            ApplicationStatusHistory.application_id.label("application_id"),
            func.max(ApplicationStatusHistory.changed_at).label("entered_at"),
        )
        .where(ApplicationStatusHistory.status == applied)
        .group_by(ApplicationStatusHistory.application_id)
        .subquery()
    )
    applied_since = func.coalesce(entered_applied.c.entered_at, Application.created_at)

    result = await db.execute(
        select(func.count(Application.id))
        .outerjoin(entered_applied, entered_applied.c.application_id == Application.id)
        .where(
            Application.user_id == user_id,
            Application.status == applied,
            applied_since < cutoff,
        )
    )
    return result.scalar_one()


def _format_pipeline(counts: dict[str, int]) -> str:
    parts = [
        f"{counts.get(ApplicationStatus.RESEARCHING.value, 0)} researching",
        f"{counts.get(ApplicationStatus.APPLIED.value, 0)} applied",
        f"{counts.get(ApplicationStatus.INTERVIEW.value, 0)} in interview",
        _plural(counts.get(ApplicationStatus.OFFER.value, 0), "offer"),
        f"{counts.get(ApplicationStatus.REJECTED.value, 0)} rejected",
    ]
    # Spec wording has no withdrawn bucket; show it only when it is non-zero
    # so the counts still add up to the user's total.
    withdrawn = counts.get(ApplicationStatus.WITHDRAWN.value, 0)
    if withdrawn:
        parts.append(f"{withdrawn} withdrawn")
    return "📊 Pipeline: " + ", ".join(parts)


def _format_recent(count: int) -> str:
    if count == 0:
        return "🔄 Status changes in the last 24 hours: None"
    return f"🔄 {_plural(count, 'status change')} in the last 24 hours"


def _format_follow_up(count: int) -> str:
    verb = "needs" if count == 1 else "need"
    return f"⏭️ {_plural(count, 'application')} {verb} follow-up"


def _format_inbox(count: int) -> str:
    word = "vacancy" if count == 1 else "vacancies"
    return f"📥 {count} new {word} in Inbox"


def _dashboard_line() -> str:
    base_url = get_settings().JOBBI_PUBLIC_URL.rstrip("/")
    return f"🔗 Open your dashboard: {base_url}/dashboard"


async def build_summary(
    db: AsyncSession, user_id: str, now: datetime | None = None
) -> str:
    """Return the summary message text for a user.

    Args:
        db: Async session.
        user_id: Jobbi user id.
        now: Reference time (naive UTC or tz-aware). Defaults to current UTC
            time; injectable for tests.
    """
    reference = _to_naive_utc(now or datetime.now(timezone.utc))

    counts = await _count_by_status(db, user_id)
    # Same number as the Inbox badge.
    new_vacancies = await count_new(db, user_id)
    if sum(counts.values()) == 0:
        lines = [EMPTY_STATE_MESSAGE]
        if new_vacancies:
            lines.append(_format_inbox(new_vacancies))
        lines.extend(["", _dashboard_line()])
        return "\n".join(lines)

    recent = await _count_recent_status_changes(
        db, user_id, reference - RECENT_ACTIVITY_WINDOW
    )
    follow_ups = await _count_follow_ups(db, user_id, reference - FOLLOW_UP_AFTER)

    lines = [
        SUMMARY_HEADER,
        "",
        _format_pipeline(counts),
        _format_recent(recent),
    ]
    if follow_ups:
        lines.append(_format_follow_up(follow_ups))
    if new_vacancies:
        lines.append(_format_inbox(new_vacancies))
    lines.extend(["", _dashboard_line()])
    return "\n".join(lines)
