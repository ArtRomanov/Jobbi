from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ApplicationStatus
from app.models.application import Application, ApplicationStatusHistory
from app.models.user import User
from app.services.summary_service import (
    EMPTY_STATE_MESSAGE,
    SUMMARY_HEADER,
    build_summary,
)

# Fixed reference time; stored timestamps are naive UTC.
NOW = datetime(2026, 6, 15, 12, 0, 0)
LONG_AGO = NOW - timedelta(days=30)

type MakeUser = Callable[..., Awaitable[User]]
type HistoryEntry = tuple[ApplicationStatus, datetime]


@pytest.fixture
async def user(make_user: MakeUser) -> User:
    return await make_user()


@pytest.fixture
def add_application(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[Application]]:
    """Insert an application with explicit created_at and status history."""

    async def _add(
        user_id: str,
        status: ApplicationStatus,
        *,
        created_at: datetime = LONG_AGO,
        history: list[HistoryEntry] | None = None,
    ) -> Application:
        app = Application(
            user_id=user_id,
            company_name="Acme",
            role_title="Engineer",
            status=status.value,
            created_at=created_at,
            updated_at=created_at,
        )
        db_session.add(app)
        await db_session.flush()
        for entry_status, changed_at in history or []:
            db_session.add(
                ApplicationStatusHistory(
                    application_id=app.id,
                    status=entry_status.value,
                    changed_at=changed_at,
                )
            )
        await db_session.commit()
        return app

    return _add


type AddApplication = Callable[..., Awaitable[Application]]


def _line(summary: str, prefix: str) -> str | None:
    return next((ln for ln in summary.splitlines() if ln.startswith(prefix)), None)


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------


async def test_empty_state(db_session: AsyncSession, user: User) -> None:
    summary = await build_summary(db_session, user.id, now=NOW)

    assert summary.startswith(EMPTY_STATE_MESSAGE)
    assert SUMMARY_HEADER not in summary
    assert "/dashboard" in summary


async def test_other_users_applications_not_counted(
    db_session: AsyncSession,
    make_user: MakeUser,
    add_application: AddApplication,
) -> None:
    me, someone_else = await make_user(), await make_user()
    await add_application(someone_else.id, ApplicationStatus.APPLIED)

    summary = await build_summary(db_session, me.id, now=NOW)

    assert summary.startswith(EMPTY_STATE_MESSAGE)


# ---------------------------------------------------------------------------
# Pipeline counts
# ---------------------------------------------------------------------------


async def test_pipeline_counts_per_stage(
    db_session: AsyncSession, user: User, add_application: AddApplication
) -> None:
    stages = (
        [ApplicationStatus.RESEARCHING] * 3
        + [ApplicationStatus.APPLIED] * 2
        + [ApplicationStatus.INTERVIEW]
        + [ApplicationStatus.OFFER]
        + [ApplicationStatus.REJECTED] * 4
    )
    for stage in stages:
        await add_application(user.id, stage)

    summary = await build_summary(db_session, user.id, now=NOW)

    assert summary.splitlines()[0] == SUMMARY_HEADER
    assert _line(summary, "📊") == (
        "📊 Pipeline: 3 researching, 2 applied, 1 in interview, 1 offer, 4 rejected"
    )


async def test_pipeline_pluralizes_offers(
    db_session: AsyncSession, user: User, add_application: AddApplication
) -> None:
    for _ in range(2):
        await add_application(user.id, ApplicationStatus.OFFER)

    summary = await build_summary(db_session, user.id, now=NOW)

    assert "2 offers" in summary


@pytest.mark.parametrize(
    ("withdrawn", "expected_suffix"),
    [(0, None), (2, "2 withdrawn")],
)
async def test_pipeline_withdrawn_only_when_nonzero(
    db_session: AsyncSession,
    user: User,
    add_application: AddApplication,
    withdrawn: int,
    expected_suffix: str | None,
) -> None:
    await add_application(user.id, ApplicationStatus.RESEARCHING)
    for _ in range(withdrawn):
        await add_application(user.id, ApplicationStatus.WITHDRAWN)

    summary = await build_summary(db_session, user.id, now=NOW)

    pipeline = _line(summary, "📊")
    assert pipeline is not None
    if expected_suffix is None:
        assert "withdrawn" not in pipeline
    else:
        assert pipeline.endswith(f", {expected_suffix}")


# ---------------------------------------------------------------------------
# Recent activity (24h window)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("changed_at", "expected_line"),
    [
        (NOW - timedelta(hours=1), "🔄 1 status change in the last 24 hours"),
        (NOW - timedelta(hours=24), "🔄 1 status change in the last 24 hours"),
        (
            NOW - timedelta(hours=24, seconds=1),
            "🔄 Status changes in the last 24 hours: None",
        ),
    ],
    ids=["inside", "exact-boundary-inclusive", "just-outside"],
)
async def test_recent_activity_window_boundary(
    db_session: AsyncSession,
    user: User,
    add_application: AddApplication,
    changed_at: datetime,
    expected_line: str,
) -> None:
    await add_application(
        user.id,
        ApplicationStatus.INTERVIEW,
        history=[(ApplicationStatus.INTERVIEW, changed_at)],
    )

    summary = await build_summary(db_session, user.id, now=NOW)

    assert _line(summary, "🔄") == expected_line


async def test_recent_activity_counts_all_changes_in_window(
    db_session: AsyncSession, user: User, add_application: AddApplication
) -> None:
    await add_application(
        user.id,
        ApplicationStatus.INTERVIEW,
        history=[
            (ApplicationStatus.RESEARCHING, NOW - timedelta(hours=20)),
            (ApplicationStatus.APPLIED, NOW - timedelta(hours=10)),
            (ApplicationStatus.INTERVIEW, NOW - timedelta(hours=2)),
        ],
    )
    await add_application(
        user.id,
        ApplicationStatus.REJECTED,
        history=[(ApplicationStatus.REJECTED, NOW - timedelta(days=3))],
    )

    summary = await build_summary(db_session, user.id, now=NOW)

    assert _line(summary, "🔄") == "🔄 3 status changes in the last 24 hours"


async def test_now_accepts_tz_aware_datetime(
    db_session: AsyncSession, user: User, add_application: AddApplication
) -> None:
    await add_application(
        user.id,
        ApplicationStatus.INTERVIEW,
        history=[(ApplicationStatus.INTERVIEW, NOW - timedelta(hours=1))],
    )
    # Same instant as NOW, expressed in UTC+2.
    aware_now = NOW.replace(tzinfo=timezone.utc).astimezone(
        timezone(timedelta(hours=2))
    )

    summary = await build_summary(db_session, user.id, now=aware_now)

    assert _line(summary, "🔄") == "🔄 1 status change in the last 24 hours"


# ---------------------------------------------------------------------------
# Follow-up (Applied for more than 7 days)
# ---------------------------------------------------------------------------


async def test_follow_up_from_status_history(
    db_session: AsyncSession, user: User, add_application: AddApplication
) -> None:
    await add_application(
        user.id,
        ApplicationStatus.APPLIED,
        history=[(ApplicationStatus.APPLIED, NOW - timedelta(days=8))],
    )

    summary = await build_summary(db_session, user.id, now=NOW)

    assert _line(summary, "⏭️") == "⏭️ 1 application needs follow-up"


async def test_follow_up_falls_back_to_created_at(
    db_session: AsyncSession, user: User, add_application: AddApplication
) -> None:
    await add_application(
        user.id, ApplicationStatus.APPLIED, created_at=NOW - timedelta(days=8)
    )
    await add_application(
        user.id, ApplicationStatus.APPLIED, created_at=NOW - timedelta(days=9)
    )

    summary = await build_summary(db_session, user.id, now=NOW)

    assert _line(summary, "⏭️") == "⏭️ 2 applications need follow-up"


async def test_follow_up_uses_history_over_old_created_at(
    db_session: AsyncSession, user: User, add_application: AddApplication
) -> None:
    # Created long ago, but only entered Applied 2 days ago.
    await add_application(
        user.id,
        ApplicationStatus.APPLIED,
        created_at=LONG_AGO,
        history=[
            (ApplicationStatus.RESEARCHING, LONG_AGO),
            (ApplicationStatus.APPLIED, NOW - timedelta(days=2)),
        ],
    )

    summary = await build_summary(db_session, user.id, now=NOW)

    assert _line(summary, "⏭️") is None


async def test_follow_up_uses_latest_applied_entry(
    db_session: AsyncSession, user: User, add_application: AddApplication
) -> None:
    # Applied 20 days ago, moved to interview, then back to Applied 3 days ago.
    await add_application(
        user.id,
        ApplicationStatus.APPLIED,
        history=[
            (ApplicationStatus.APPLIED, NOW - timedelta(days=20)),
            (ApplicationStatus.INTERVIEW, NOW - timedelta(days=10)),
            (ApplicationStatus.APPLIED, NOW - timedelta(days=3)),
        ],
    )

    summary = await build_summary(db_session, user.id, now=NOW)

    assert _line(summary, "⏭️") is None


async def test_follow_up_ignores_apps_no_longer_applied(
    db_session: AsyncSession, user: User, add_application: AddApplication
) -> None:
    await add_application(
        user.id,
        ApplicationStatus.INTERVIEW,
        history=[
            (ApplicationStatus.APPLIED, NOW - timedelta(days=20)),
            (ApplicationStatus.INTERVIEW, NOW - timedelta(days=10)),
        ],
    )

    summary = await build_summary(db_session, user.id, now=NOW)

    assert _line(summary, "⏭️") is None


@pytest.mark.parametrize(
    ("entered_applied", "expects_follow_up"),
    [
        (NOW - timedelta(days=7, seconds=1), True),
        (NOW - timedelta(days=7), False),
        (NOW - timedelta(days=6), False),
    ],
    ids=["just-over-7d", "exactly-7d", "6d"],
)
async def test_follow_up_seven_day_boundary(
    db_session: AsyncSession,
    user: User,
    add_application: AddApplication,
    entered_applied: datetime,
    expects_follow_up: bool,
) -> None:
    await add_application(
        user.id,
        ApplicationStatus.APPLIED,
        history=[(ApplicationStatus.APPLIED, entered_applied)],
    )

    summary = await build_summary(db_session, user.id, now=NOW)

    assert (_line(summary, "⏭️") is not None) is expects_follow_up


async def test_follow_up_line_omitted_when_zero(
    db_session: AsyncSession, user: User, add_application: AddApplication
) -> None:
    await add_application(user.id, ApplicationStatus.RESEARCHING)

    summary = await build_summary(db_session, user.id, now=NOW)

    assert "follow-up" not in summary
    assert summary.splitlines()[-1].startswith("🔗")
