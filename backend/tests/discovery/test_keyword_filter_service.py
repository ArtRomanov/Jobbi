"""Pre-AI keyword filter in the worker: pending posts that name none of the
user's keywords are deleted before the AI call; their seen keys stay with
`filtered_at` (file-backed SQLite, fake Groq, fixed clock)."""

from datetime import datetime, timedelta

import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.discovery.service import (
    ForwardedChannel,
    check_all,
    evaluate_pending,
    run_initial_scans,
    store_forwarded_post,
)
from app.discovery.types import RawPost
from app.models.vacancy_search_settings import VacancySearchSettings
from app.models.vacancy_seen_key import VacancySeenKey
from tests.discovery.board_stubs import GreenhouseBoard
from tests.discovery.test_board_service import make_board
from tests.discovery.test_service import (
    CHAT_ID,
    CONFIG,
    NOW,
    at,
    make_pending,
    make_source,
    make_user,
    vacancies,
)
from tests.discovery.test_web_service import check, make_web_source, queue_rows
from tests.discovery.web_stubs import Sites, WebSite

KEYWORDS = ["react", "фронт", "front end"]


@pytest.fixture
def site(respx_mock: respx.MockRouter) -> WebSite:
    return Sites(respx_mock).add(WebSite())


@pytest.fixture
def gh(respx_mock: respx.MockRouter) -> GreenhouseBoard:
    board = GreenhouseBoard()
    board.mount(respx_mock)
    return board


async def filtered_keys(db: async_sessionmaker[AsyncSession]) -> dict[str, datetime]:
    """Seen keys the filter marked, with their `filtered_at`."""
    async with db() as session:
        rows = await session.execute(
            select(VacancySeenKey.external_key, VacancySeenKey.filtered_at).where(
                VacancySeenKey.filtered_at.is_not(None)
            )
        )
        return {key: filtered_at for key, filtered_at in rows}


async def _evaluate(factory, ai, sleep, **kwargs):
    return await evaluate_pending(
        factory, ai, at(NOW), config=CONFIG, sleep=sleep, **kwargs
    )


# --- telegram posts ----------------------------------------------------------------


async def test_post_without_a_keyword_is_deleted_without_an_ai_call(
    factory, db, ai, sleep
) -> None:
    user_id = await make_user(db, keywords=KEYWORDS)
    await make_pending(db, user_id, 1, text="MATCH Senior React developer")
    await make_pending(db, user_id, 1, text="MATCH Java backend", start=2)
    await make_pending(db, user_id, 1, text="MATCH Фронтенд-разработчик", start=3)
    await make_pending(db, user_id, 1, text="MATCH Front-end engineer", start=4)

    report = await _evaluate(factory, ai, sleep)

    assert report.posts_filtered == 1
    assert sorted(ai.posts_sent) == [
        "MATCH Front-end engineer 4",
        "MATCH Senior React developer 1",
        "MATCH Фронтенд-разработчик 3",
    ]
    rows = await vacancies(db)
    assert [r.external_key for r in rows] == [
        "tg:other/1",
        "tg:other/3",
        "tg:other/4",
    ]
    assert all(r.state == "new" for r in rows)
    # Only its seen key stays, so the post never comes back.
    assert await filtered_keys(db) == {"tg:other/2": NOW}


async def test_filtered_post_does_not_come_back_when_keywords_change(
    factory, db, ai, sleep
) -> None:
    user_id = await make_user(db, keywords=["react"])
    await make_pending(db, user_id, 1, text="MATCH Java backend")
    await _evaluate(factory, ai, sleep)
    async with db() as session:
        row = await session.get(VacancySearchSettings, user_id)
        assert row is not None
        row.keywords = ["java"]
        await session.commit()

    report = await _evaluate(factory, ai, sleep)

    assert ai.calls == [] and report.posts_filtered == 0
    assert await vacancies(db) == []
    assert set(await filtered_keys(db)) == {"tg:other/1"}


async def test_digest_with_one_matching_line_is_kept(factory, db, ai, sleep) -> None:
    user_id = await make_user(db, keywords=["react"])
    await make_pending(
        db,
        user_id,
        1,
        text="Jobs of the week\n1. Senior Java engineer\n2. MATCH React developer",
    )

    report = await _evaluate(factory, ai, sleep)

    assert report.posts_filtered == 0
    assert len(ai.posts_sent) == 1
    [card] = await vacancies(db)
    assert card.state == "new"
    assert await filtered_keys(db) == {}


@pytest.mark.parametrize(
    ("keywords", "enabled"),
    [(["react"], False), ([], True), ([], False)],
    ids=["switch-off", "empty-list", "both"],
)
async def test_filter_off_sends_every_post_to_the_ai(
    factory, db, ai, sleep, keywords: list[str], enabled: bool
) -> None:
    user_id = await make_user(db, keywords=keywords, keyword_filter_enabled=enabled)
    await make_pending(db, user_id, 2, text="MATCH Java backend")

    report = await _evaluate(factory, ai, sleep)

    assert report.posts_filtered == 0
    assert len(ai.posts_sent) == 2
    assert len(await vacancies(db)) == 2
    assert await filtered_keys(db) == {}


async def test_filter_is_per_user(factory, db, ai, sleep) -> None:
    strict = await make_user(db, keywords=["react"])
    open_user = await make_user(db, email="u2@example.com")
    await make_pending(db, strict, 1, text="MATCH Java backend")
    await make_pending(db, open_user, 1, text="MATCH Java backend", start=2)

    report = await _evaluate(factory, ai, sleep)

    assert report.posts_filtered == 1
    [card] = await vacancies(db)
    assert card.user_id == open_user


# --- forwarded posts ---------------------------------------------------------------


async def _forward(factory, user_id: str, text: str) -> None:
    post = RawPost(
        external_key="tgc:1234567890/1",
        url="https://t.me/c/1234567890/1",
        job_link=None,
        title=None,
        company=None,
        text=text,
        posted_at=NOW - timedelta(hours=3),
        links=(),
    )
    await store_forwarded_post(
        factory,
        user_id,
        ForwardedChannel(handle="c1234567890", label="Secret Jobs"),
        post,
        NOW,
        chat_id=CHAT_ID,
        message_id=31,
    )


async def test_forwarded_post_is_never_filtered_in_the_minute_run(
    factory, db, ai, sleep
) -> None:
    user_id = await make_user(db, keywords=["react"])
    await _forward(factory, user_id, "MATCH HIGH Java backend")

    report = await run_initial_scans(
        factory, None, ai, at(NOW), config=CONFIG, sleep=sleep
    )

    assert report.posts_filtered == 0
    assert ai.posts_sent == ["MATCH HIGH Java backend"]
    [card] = await vacancies(db)
    assert card.state == "new"


async def test_forwarded_post_is_never_filtered_in_the_hourly_run(
    factory, db, ai, sleep
) -> None:
    user_id = await make_user(db, keywords=["react"])
    await _forward(factory, user_id, "MATCH HIGH Java backend")
    await make_pending(db, user_id, 1, text="MATCH Java backend")

    report = await _evaluate(factory, ai, sleep)

    # The watched channel's post is filtered; the forwarded one is rated.
    assert report.posts_filtered == 1
    assert ai.posts_sent == ["MATCH HIGH Java backend"]
    [card] = await vacancies(db)
    assert card.external_key == "tgc:1234567890/1"
    assert set(await filtered_keys(db)) == {"tg:other/1"}


# --- web and board sources ---------------------------------------------------------


async def test_web_row_waits_for_its_page_then_is_filtered_by_page_text(
    factory,
    db,
    site,
    http,
    ai,
    sleep,
) -> None:
    user_id = await make_user(db, keywords=["react"])
    source_id = await make_web_source(db, user_id, site)
    site.add("a", "MATCH Senior React developer")
    site.add("b", "MATCH Senior Java developer")
    await queue_rows(db, user_id, source_id, site, ["a", "b"])

    # Listing title only ("Listed a"): not filtered before the page is read.
    report = await _evaluate(factory, ai, sleep)
    assert report.posts_filtered == 0
    rows = await vacancies(db)
    assert len(rows) == 2 and all(r.needs_detail for r in rows)
    assert await filtered_keys(db) == {}

    report = await check(factory, http, ai, sleep, NOW + timedelta(minutes=1))

    assert report.posts_filtered == 1
    [sent] = ai.posts_sent
    assert sent.endswith("MATCH Senior React developer")
    [card] = await vacancies(db)
    assert card.external_key == site.key(source_id, "a")
    assert set(await filtered_keys(db)) == {site.key(source_id, "b")}


async def test_board_job_is_kept_by_a_keyword_in_its_title(
    factory,
    db,
    gh,
    http,
    ai,
    sleep,
) -> None:
    user_id = await make_user(db, keywords=["frontend"])
    await make_board(db, user_id, "greenhouse", "acme", "Acme Corp")
    recent = NOW - timedelta(days=1)
    gh.add(1, "MATCH remote role", recent, title="Frontend Engineer")
    gh.add(2, "MATCH remote role", recent, title="Java Engineer")

    report = await run_initial_scans(
        factory, http, ai, at(NOW), config=CONFIG, sleep=sleep
    )

    assert report.posts_stored == 2 and report.posts_filtered == 1
    assert len(ai.posts_sent) == 1
    [card] = await vacancies(db)
    assert card.external_key == "gh:acme/1"
    assert set(await filtered_keys(db)) == {"gh:acme/2"}


async def test_check_all_reports_filtered_posts(
    factory, db, channel, http, ai, sleep
) -> None:
    user_id = await make_user(db, keywords=["react"])
    await make_source(db, user_id, scanned=True)
    channel.add(10, "MATCH React role")
    channel.add(11, "MATCH Java role")

    report = await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

    assert report.posts_filtered == 1
    assert ai.posts_sent == ["MATCH React role"]
    assert len(await filtered_keys(db)) == 1
