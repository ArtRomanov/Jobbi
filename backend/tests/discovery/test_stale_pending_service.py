"""Stale pending posts (backlog #19 E): before each user's evaluation, pending
posts older than STALE_PENDING_AFTER are deleted without an AI call; their
seen keys stay (file-backed SQLite, fake Groq, fixed clock)."""

import logging
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.discovery.service import (
    STALE_PENDING_AFTER,
    ForwardedChannel,
    ForwardOutcome,
    check_all,
    evaluate_pending,
    run_initial_scans,
    store_forwarded_post,
)
from app.discovery.types import RawPost
from app.models.vacancy import Vacancy, VacancyCardSource
from app.models.vacancy_seen_key import VacancySeenKey
from tests.discovery.test_service import (
    CHAT_ID,
    CONFIG,
    NOW,
    at,
    make_pending,
    make_source,
    make_user,
    seen_keys,
    vacancies,
)

OLD = NOW - STALE_PENDING_AFTER - timedelta(hours=1)
FRESH = NOW - timedelta(hours=2)


def test_cutoff_is_the_seven_day_lookback() -> None:
    assert timedelta(days=7) == STALE_PENDING_AFTER


async def add_pending(
    db: async_sessionmaker[AsyncSession],
    user_id: str,
    key: str,
    *,
    posted_at: datetime,
    found_at: datetime,
    needs_detail: bool = False,
    text: str = "MATCH",
) -> str:
    """A pending row with its seen key and card source."""
    async with db() as session:
        session.add(
            VacancySeenKey(user_id=user_id, external_key=key, first_seen_at=found_at)
        )
        row = Vacancy(
            user_id=user_id,
            external_key=key,
            url=f"https://example.com/{key}",
            text=f"{text} {key}",
            posted_at=posted_at,
            found_at=found_at,
            state="pending",
            needs_detail=needs_detail,
        )
        session.add(row)
        await session.flush()
        session.add(
            VacancyCardSource(
                vacancy_id=row.id,
                source_kind="telegram",
                source_handle="other",
                label="@other",
            )
        )
        await session.commit()
        return row.id


async def card_source_ids(db: async_sessionmaker[AsyncSession]) -> set[str]:
    async with db() as session:
        return set(await session.scalars(select(VacancyCardSource.vacancy_id)))


async def _evaluate(factory, ai, sleep, **kwargs):
    return await evaluate_pending(
        factory, ai, at(NOW), config=CONFIG, sleep=sleep, **kwargs
    )


async def test_old_telegram_post_is_dropped_without_an_ai_call(
    factory, db, ai, sleep
) -> None:
    user_id = await make_user(db)
    # Found yesterday (e.g. after a worker outage) but posted 7 days + 1 h ago.
    old_id = await add_pending(
        db, user_id, "tg:other/1", posted_at=OLD, found_at=NOW - timedelta(days=1)
    )
    await add_pending(db, user_id, "tg:other/2", posted_at=FRESH, found_at=FRESH)

    report = await _evaluate(factory, ai, sleep)

    assert report.posts_expired == 1
    assert ai.posts_sent == ["MATCH tg:other/2"]
    [card] = await vacancies(db)
    assert card.external_key == "tg:other/2" and card.state == "new"
    # The seen key stays, so the post never comes back.
    assert set(await seen_keys(db)) == {"tg:other/1", "tg:other/2"}
    assert old_id not in await card_source_ids(db)


async def test_telegram_post_just_inside_the_window_is_rated(
    factory, db, ai, sleep
) -> None:
    user_id = await make_user(db)
    edge = NOW - STALE_PENDING_AFTER + timedelta(minutes=1)
    await add_pending(db, user_id, "tg:other/1", posted_at=edge, found_at=edge)

    report = await _evaluate(factory, ai, sleep)

    assert report.posts_expired == 0
    assert len(ai.posts_sent) == 1


async def test_board_job_counts_from_when_it_was_found(factory, db, ai, sleep) -> None:
    """A board job dated weeks back but found today is still open: rated.
    One found more than 7 days ago waited too long: dropped."""
    user_id = await make_user(db)
    month_ago = NOW - timedelta(days=30)
    await add_pending(db, user_id, "gh:acme/1", posted_at=month_ago, found_at=FRESH)
    await add_pending(db, user_id, "gh:acme/2", posted_at=FRESH, found_at=OLD)
    await add_pending(db, user_id, "web:s1/abc", posted_at=month_ago, found_at=OLD)

    report = await _evaluate(factory, ai, sleep)

    assert report.posts_expired == 2
    assert ai.posts_sent == ["MATCH gh:acme/1"]
    assert [r.external_key for r in await vacancies(db)] == ["gh:acme/1"]


async def test_web_row_waiting_for_its_page_is_kept(factory, db, ai, sleep) -> None:
    user_id = await make_user(db)
    await add_pending(
        db, user_id, "web:s1/abc", posted_at=OLD, found_at=OLD, needs_detail=True
    )

    report = await _evaluate(factory, ai, sleep)

    assert report.posts_expired == 0
    [row] = await vacancies(db)
    assert row.state == "pending" and row.needs_detail


async def _forward(factory, user_id: str, key: str) -> ForwardOutcome:
    post = RawPost(
        external_key=key,
        url="https://t.me/other/9",
        job_link=None,
        title=None,
        company=None,
        text="MATCH forwarded",
        posted_at=NOW - timedelta(days=20),
        links=(),
    )
    return await store_forwarded_post(
        factory,
        user_id,
        ForwardedChannel(handle="other", label="@other"),
        post,
        OLD,
        chat_id=CHAT_ID,
        message_id=31,
    )


async def test_forwarded_post_is_never_dropped(factory, db, ai, sleep) -> None:
    user_id = await make_user(db)
    assert await _forward(factory, user_id, "tg:other/9") is ForwardOutcome.ADDED

    report = await _evaluate(factory, ai, sleep)

    assert report.posts_expired == 0
    assert ai.posts_sent == ["MATCH forwarded"]
    [card] = await vacancies(db)
    assert card.state == "new"


async def test_old_channel_post_forwarded_later_is_rated(
    factory, db, ai, sleep
) -> None:
    user_id = await make_user(db)
    await add_pending(db, user_id, "tg:other/1", posted_at=OLD, found_at=OLD)
    outcome = await _forward(factory, user_id, "tg:other/1")
    assert outcome is ForwardOutcome.ALREADY_SEEN  # waits for its rating

    report = await _evaluate(factory, ai, sleep)

    assert report.posts_expired == 0
    assert ai.posts_sent == ["MATCH tg:other/1"]


async def test_minute_run_does_not_drop_stale_posts(factory, db, ai, sleep) -> None:
    user_id = await make_user(db)
    await _forward(factory, user_id, "tgc:1234567890/1")
    await add_pending(db, user_id, "tg:other/1", posted_at=OLD, found_at=OLD)

    report = await run_initial_scans(
        factory, None, ai, at(NOW), config=CONFIG, sleep=sleep
    )

    assert report.posts_expired == 0
    assert ai.posts_sent == ["MATCH forwarded"]
    rows = {r.external_key: r.state for r in await vacancies(db)}
    assert rows == {"tg:other/1": "pending", "tgc:1234567890/1": "new"}


async def test_expiry_runs_before_the_keyword_filter(factory, db, ai, sleep) -> None:
    user_id = await make_user(db, keywords=["react"])
    await add_pending(
        db, user_id, "tg:other/1", posted_at=OLD, found_at=OLD, text="Java"
    )

    report = await _evaluate(factory, ai, sleep)

    assert report.posts_expired == 1 and report.posts_filtered == 0
    assert await vacancies(db) == []


async def test_check_all_reports_and_logs_expired_posts(
    factory, db, channel, http, ai, sleep, caplog: pytest.LogCaptureFixture
) -> None:
    user_id = await make_user(db)
    await make_source(db, user_id, scanned=True)
    await make_pending(db, user_id, 1, found_at=OLD, text="SECRET")

    with caplog.at_level(logging.INFO, logger="app.discovery.service"):
        report = await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

    assert report.posts_expired == 1
    assert ai.posts_sent == []
    [line] = [
        r.getMessage() for r in caplog.records if "hourly check" in r.getMessage()
    ]
    assert "expired=1" in line
    assert "SECRET" not in caplog.text
