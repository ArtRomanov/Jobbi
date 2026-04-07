from collections import Counter
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ApplicationStatus
from app.models.application import Application, ApplicationStatusHistory

ALL_STATUSES = [
    ApplicationStatus.RESEARCHING,
    ApplicationStatus.APPLIED,
    ApplicationStatus.INTERVIEW,
    ApplicationStatus.OFFER,
    ApplicationStatus.REJECTED,
    ApplicationStatus.WITHDRAWN,
]

RESPONSE_STATUSES = {
    ApplicationStatus.INTERVIEW.value,
    ApplicationStatus.OFFER.value,
    ApplicationStatus.REJECTED.value,
}

INACTIVE_STATUSES = {
    ApplicationStatus.REJECTED.value,
    ApplicationStatus.WITHDRAWN.value,
}


def resolve_date_range(range_key: str, earliest: datetime | None) -> tuple[datetime, datetime]:
    """Convert a range preset to (from_dt, to_dt) naive UTC datetimes.

    Returns naive datetimes to match SQLite's stored timestamps (which are naive).
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    to_dt = now

    if range_key == "7d":
        from_dt = now - timedelta(days=7)
    elif range_key == "30d":
        from_dt = now - timedelta(days=30)
    elif range_key == "90d":
        from_dt = now - timedelta(days=90)
    elif range_key == "all":
        if earliest is not None:
            from_dt = earliest.replace(tzinfo=None) if earliest.tzinfo else earliest
        else:
            from_dt = now
    else:
        from_dt = now - timedelta(days=30)

    return from_dt, to_dt


def select_granularity(range_key: str, span_days: int) -> str:
    """Pick chart granularity based on the range."""
    if range_key in ("7d", "30d"):
        return "daily"
    if range_key == "90d":
        return "weekly"
    # all
    if span_days < 365:
        return "weekly"
    return "monthly"


def _bucket_date(d: date, granularity: str) -> date:
    """Round a date down to its bucket start."""
    if granularity == "daily":
        return d
    if granularity == "weekly":
        # Monday as week start
        return d - timedelta(days=d.weekday())
    if granularity == "monthly":
        return d.replace(day=1)
    return d


def _generate_buckets(from_dt: datetime, to_dt: datetime, granularity: str) -> list[date]:
    """Generate all bucket start dates between from and to (inclusive)."""
    buckets: list[date] = []
    current = _bucket_date(from_dt.date(), granularity)
    end = _bucket_date(to_dt.date(), granularity)

    while current <= end:
        buckets.append(current)
        if granularity == "daily":
            current = current + timedelta(days=1)
        elif granularity == "weekly":
            current = current + timedelta(days=7)
        elif granularity == "monthly":
            # Add one month (handles year rollover)
            year = current.year + (current.month // 12)
            month = (current.month % 12) + 1
            current = date(year, month, 1)

    return buckets


async def get_metrics(
    db: AsyncSession, user_id: str, range_key: str
) -> dict:
    """Compute all metrics for the user within the given date range."""
    # Find earliest application for "all" range
    earliest_q = await db.execute(
        select(func.min(Application.created_at)).where(Application.user_id == user_id)
    )
    earliest = earliest_q.scalar_one_or_none()

    from_dt, to_dt = resolve_date_range(range_key, earliest)

    # Fetch all user's applications in range
    apps_q = await db.execute(
        select(Application).where(
            Application.user_id == user_id,
            Application.created_at >= from_dt,
            Application.created_at <= to_dt,
        )
    )
    apps = list(apps_q.scalars().all())
    app_ids = [app.id for app in apps]

    # Fetch status history for these apps to compute response rate and interviews
    history_statuses_by_app: dict[str, set[str]] = {}
    if app_ids:
        history_q = await db.execute(
            select(
                ApplicationStatusHistory.application_id,
                ApplicationStatusHistory.status,
            ).where(ApplicationStatusHistory.application_id.in_(app_ids))
        )
        for app_id, status in history_q.all():
            history_statuses_by_app.setdefault(app_id, set()).add(status)

    # Also include the current status of each app (in case history is missing entries)
    for app in apps:
        history_statuses_by_app.setdefault(app.id, set()).add(app.status)

    # KPIs
    total = len(apps)
    active = sum(1 for app in apps if app.status not in INACTIVE_STATUSES)

    apps_with_response = sum(
        1
        for app_id, statuses in history_statuses_by_app.items()
        if statuses & RESPONSE_STATUSES
    )
    response_rate = (apps_with_response / total) if total > 0 else 0.0

    interviews = sum(
        1
        for statuses in history_statuses_by_app.values()
        if ApplicationStatus.INTERVIEW.value in statuses
    )

    # Pipeline (current status counts, zero-fill all 6)
    status_counts = Counter(app.status for app in apps)
    pipeline = [
        {"status": s.value, "count": status_counts.get(s.value, 0)}
        for s in ALL_STATUSES
    ]

    # Trend
    span_days = max((to_dt - from_dt).days, 1)
    granularity = select_granularity(range_key, span_days)
    buckets = _generate_buckets(from_dt, to_dt, granularity)
    bucket_counts: Counter[date] = Counter()
    for app in apps:
        bucket_start = _bucket_date(app.created_at.date(), granularity)
        bucket_counts[bucket_start] += 1

    trend_points = [
        {"date": b, "count": bucket_counts.get(b, 0)} for b in buckets
    ]

    return {
        "range": range_key,
        "from_date": from_dt.date(),
        "to_date": to_dt.date(),
        "kpis": {
            "total_applications": total,
            "active": active,
            "response_rate": round(response_rate, 4),
            "interviews": interviews,
        },
        "pipeline": pipeline,
        "trend": {
            "granularity": granularity,
            "points": trend_points,
        },
    }
