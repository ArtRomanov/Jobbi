"""Worker runs for Greenhouse, Lever and Teamtailor boards (respx, file SQLite)."""

from datetime import timedelta

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.discovery.fetchers import greenhouse
from app.discovery.service import check_all, run_initial_scans
from app.models.vacancy import VacancyCardSource
from app.models.vacancy_seen_key import VacancySeenKey
from app.models.vacancy_source import VacancySource
from tests.discovery.board_stubs import GreenhouseBoard, LeverBoard, TeamtailorBoard
from tests.discovery.fake_bot import FakeBot
from tests.discovery.test_service import (
    CHAT_ID,
    CONFIG,
    NOW,
    TrackingFactory,
    at,
    get_source,
    link_telegram,
    make_user,
    seen_keys,
    vacancies,
)

LATER = NOW + timedelta(hours=1)
RECENT = NOW - timedelta(days=2)
OLD = NOW - timedelta(days=30)


async def make_board(
    db: async_sessionmaker[AsyncSession],
    user_id: str,
    kind: str,
    handle: str,
    display_name: str,
) -> str:
    async with db() as session:
        source = VacancySource(
            user_id=user_id,
            kind=kind,
            handle=handle,
            default_name=display_name,
            display_name=display_name,
        )
        session.add(source)
        await session.commit()
        return source.id


@pytest.fixture
def gh(respx_mock: respx.MockRouter) -> GreenhouseBoard:
    board = GreenhouseBoard()
    board.mount(respx_mock)
    return board


@pytest.fixture
def lever_board(respx_mock: respx.MockRouter) -> LeverBoard:
    board = LeverBoard()
    board.mount(respx_mock)
    return board


@pytest.fixture
def tt_board(respx_mock: respx.MockRouter) -> TeamtailorBoard:
    board = TeamtailorBoard()
    board.mount(respx_mock)
    return board


async def card_sources(db: async_sessionmaker[AsyncSession]) -> list[tuple]:
    async with db() as session:
        rows = await session.execute(
            select(
                VacancyCardSource.source_id,
                VacancyCardSource.source_kind,
                VacancyCardSource.source_handle,
                VacancyCardSource.label,
            )
        )
        return [tuple(r) for r in rows]


# --- Greenhouse initial scan ---------------------------------------------------------


class TestGreenhouseInitialScan:
    async def test_records_every_listed_job_but_only_recent_ones_become_pending(
        self, factory, db, gh, http, ai, sleep
    ) -> None:
        user_id = await make_user(db, description=None)
        source_id = await make_board(db, user_id, "greenhouse", "acme", "Acme Corp")
        gh.add(1, "MATCH recent", RECENT, title="Frontend Engineer")
        gh.add(2, "MATCH old", OLD)
        gh.add(3, "MATCH no date", None)
        gh.add(4, "MATCH just inside", NOW - timedelta(days=7) + timedelta(minutes=1))

        report = await run_initial_scans(
            factory, http, ai, at(NOW), config=CONFIG, sleep=sleep
        )

        # Every listed job is remembered, so none can come back as "new".
        assert set(await seen_keys(db)) == {
            "gh:acme/1",
            "gh:acme/2",
            "gh:acme/3",
            "gh:acme/4",
        }
        rows = await vacancies(db)
        assert [r.external_key for r in rows] == ["gh:acme/1", "gh:acme/4"]
        first = rows[0]
        assert first.state == "pending"
        assert first.from_initial_scan is True
        assert first.alert_handled_at is None  # summarised once rated
        assert first.title == "Frontend Engineer"
        assert first.company == "Acme Corp"
        assert first.text == "MATCH recent"
        assert first.posted_at == RECENT
        assert first.url.startswith("https://job-boards.greenhouse.io/acme/jobs/1")
        assert first.job_link == "https://job-boards.greenhouse.io/acme/jobs/1"
        assert (
            await card_sources(db)
            == [(source_id, "greenhouse", "acme", "Acme Corp")] * 2
        )
        # Descriptions are fetched only for jobs that become posts.
        assert sorted(gh.detail_requests) == [1, 4]
        assert sleep.calls == [greenhouse.JOB_DETAIL_PAUSE_S]
        source = await get_source(db, source_id)
        assert source.initial_scan_completed_at == NOW
        assert source.last_checked_at == NOW
        assert source.failing_since is None
        assert report.posts_stored == 2
        assert ai.calls == []

    async def test_initial_scan_matches_are_handled_by_the_alert_step(
        self, factory, db, gh, http, ai, sleep
    ) -> None:
        user_id = await make_user(db)
        await make_board(db, user_id, "greenhouse", "acme", "Acme Corp")
        gh.add(1, "MATCH HIGH", RECENT)
        gh.add(2, "news", RECENT)

        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        [row] = await vacancies(db)
        assert row.external_key == "gh:acme/1"
        assert row.state == "new"
        assert row.from_initial_scan is True
        assert row.alert_handled_at == NOW
        keys = await seen_keys(db)
        assert keys["gh:acme/1"] == NOW and keys["gh:acme/2"] == NOW

    async def test_one_second_between_job_detail_requests(
        self, factory, db, gh, http, ai, sleep
    ) -> None:
        user_id = await make_user(db, description=None)
        await make_board(db, user_id, "greenhouse", "acme", "Acme Corp")
        for job_id in range(1, 5):
            gh.add(job_id, f"job {job_id}", RECENT)

        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        assert len(gh.detail_requests) == 4
        assert sleep.calls == [1.0, 1.0, 1.0]

    async def test_job_closed_before_its_detail_is_skipped(
        self, factory, db, gh, http, ai, sleep
    ) -> None:
        user_id = await make_user(db, description=None)
        source_id = await make_board(db, user_id, "greenhouse", "acme", "Acme Corp")
        gh.add(1, "gone", RECENT)
        gh.add(2, "still open", RECENT)
        gh.missing_details.add(1)

        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        assert [r.external_key for r in await vacancies(db)] == ["gh:acme/2"]
        assert set(await seen_keys(db)) == {"gh:acme/2"}
        source = await get_source(db, source_id)
        assert source.initial_scan_completed_at == NOW
        assert source.last_error is None

    async def test_readded_board_does_not_refetch_or_reshow_known_jobs(
        self, factory, db, gh, http, ai, sleep
    ) -> None:
        user_id = await make_user(db, description=None)
        await make_board(db, user_id, "greenhouse", "acme", "Acme Corp")
        async with db() as session:
            session.add(
                VacancySeenKey(
                    user_id=user_id, external_key="gh:acme/1", first_seen_at=OLD
                )
            )
            await session.commit()
        gh.add(1, "MATCH seen before", RECENT)
        gh.add(2, "MATCH new", RECENT)

        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        assert gh.detail_requests == [2]
        assert [r.external_key for r in await vacancies(db)] == ["gh:acme/2"]


# --- hourly check ------------------------------------------------------------------


class TestBoardHourlyCheck:
    async def test_picks_up_only_a_newly_listed_job(
        self, factory, db, gh, http, ai, sleep
    ) -> None:
        user_id = await make_user(db)
        await make_board(db, user_id, "greenhouse", "acme", "Acme Corp")
        gh.add(1, "MATCH recent", RECENT)
        gh.add(2, "MATCH old", OLD)
        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)
        ai.calls.clear()
        gh.detail_requests.clear()

        gh.add(3, "MATCH HIGH brand new", LATER - timedelta(minutes=5))
        report = await check_all(
            factory, http, ai, at(LATER), config=CONFIG, sleep=sleep
        )

        # Only the new job's description is fetched and evaluated.
        assert gh.detail_requests == [3]
        assert ai.posts_sent and all("brand new" in text for text in ai.posts_sent)
        rows = {r.external_key: r for r in await vacancies(db)}
        assert set(rows) == {"gh:acme/1", "gh:acme/3"}
        new = rows["gh:acme/3"]
        assert new.state == "new"
        assert new.from_initial_scan is False
        assert new.alert_handled_at == LATER  # handled by the run's alert step
        assert report.new_card_ids == {user_id: [new.id]}
        assert report.posts_stored == 1

        # A further check finds nothing new.
        gh.detail_requests.clear()
        ai.calls.clear()
        await check_all(
            factory,
            http,
            ai,
            at(LATER + timedelta(hours=1)),
            config=CONFIG,
            sleep=sleep,
        )
        assert gh.detail_requests == []
        assert ai.calls == []

    async def test_undated_new_job_gets_the_check_time(
        self, factory, db, gh, http, ai, sleep
    ) -> None:
        user_id = await make_user(db, description=None)
        await make_board(db, user_id, "greenhouse", "acme", "Acme Corp")
        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        gh.add(9, "no date", None)
        await check_all(factory, http, ai, at(LATER), config=CONFIG, sleep=sleep)

        [row] = await vacancies(db)
        assert row.external_key == "gh:acme/9"
        assert row.posted_at == LATER
        assert row.from_initial_scan is False

    async def test_skips_board_still_in_its_first_scan(
        self, factory, db, gh, http, ai, sleep
    ) -> None:
        user_id = await make_user(db, description=None)
        await make_board(db, user_id, "greenhouse", "acme", "Acme Corp")
        gh.add(1, "job", RECENT)

        await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        assert gh.list_requests == 0


# --- alerts ----------------------------------------------------------------------


async def test_board_first_scan_is_summarised_per_board_then_hourly_alert(
    factory, db, gh, lever_board, http, ai, sleep
) -> None:
    bot = FakeBot(open_transactions=factory.open_transactions)
    user_id = await make_user(db)
    await link_telegram(db, user_id)
    await make_board(db, user_id, "greenhouse", "acme", "Acme Corp")
    await make_board(db, user_id, "lever", "acme-labs", "Acme Labs")
    gh.add(1, "MATCH HIGH gh first scan", RECENT)
    lever_board.add("a", "MATCH HIGH lever first scan", RECENT)

    await run_initial_scans(
        factory, http, ai, at(NOW), config=CONFIG, sleep=sleep, bot=bot
    )

    rows = await vacancies(db)
    assert [r.state for r in rows] == ["new", "new"]
    assert all(r.from_initial_scan and r.alert_handled_at == NOW for r in rows)
    assert [text.splitlines()[0] for text in bot.texts] == [
        "🔎 First scan of source Acme Corp: 1 matching vacancy",
        "🔎 First scan of source Acme Labs: 1 matching vacancy",
    ]
    assert [text.splitlines()[-1].rsplit("?", 1)[1] for text in bot.texts] == [
        "source=greenhouse%3Aacme",
        "source=lever%3Aacme-labs",
    ]

    gh.add(2, "MATCH HIGH gh hourly", LATER, title="Frontend Engineer")
    await check_all(factory, http, ai, at(LATER), config=CONFIG, sleep=sleep, bot=bot)

    assert len(bot.sent) == 3
    chat_id, text = bot.sent[2]
    assert chat_id == CHAT_ID
    assert text.splitlines()[0] == "🔎 1 new vacancy"
    assert "Frontend Engineer" in text
    assert bot.violations == 0


# --- read errors -------------------------------------------------------------------


class TestBoardReadErrors:
    @pytest.mark.parametrize(
        ("status", "message"),
        [
            (404, "Job board not found"),
            (500, "Could not reach the source"),
            (429, "Could not reach the source"),
        ],
    )
    async def test_initial_scan_failure_is_recorded(
        self, factory, db, gh, http, ai, sleep, status, message
    ) -> None:
        user_id = await make_user(db, description=None)
        source_id = await make_board(db, user_id, "greenhouse", "acme", "Acme Corp")
        gh.fail_list = status

        report = await run_initial_scans(
            factory, http, ai, at(NOW), config=CONFIG, sleep=sleep
        )

        source = await get_source(db, source_id)
        assert source.last_error == message
        assert source.failing_since == NOW
        assert source.initial_scan_completed_at is None  # retried later
        assert report.sources_failed == 1
        assert await seen_keys(db) == {}

    async def test_hourly_failure_keeps_first_failure_time_and_recovers(
        self, factory, db, lever_board, http, ai, sleep
    ) -> None:
        user_id = await make_user(db, description=None)
        source_id = await make_board(db, user_id, "lever", "acme-labs", "Acme Labs")
        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        lever_board.status = 404
        await check_all(factory, http, ai, at(LATER), config=CONFIG, sleep=sleep)
        await check_all(
            factory,
            http,
            ai,
            at(LATER + timedelta(hours=1)),
            config=CONFIG,
            sleep=sleep,
        )
        source = await get_source(db, source_id)
        assert source.last_error == "Job board not found"
        assert source.failing_since == LATER

        lever_board.status = 200
        await check_all(
            factory,
            http,
            ai,
            at(LATER + timedelta(hours=2)),
            config=CONFIG,
            sleep=sleep,
        )
        source = await get_source(db, source_id)
        assert source.last_error is None
        assert source.failing_since is None

    async def test_failed_job_detail_skips_only_that_job_and_is_retried(
        self, factory, db, gh, http, ai, sleep
    ) -> None:
        user_id = await make_user(db, description=None)
        source_id = await make_board(db, user_id, "greenhouse", "acme", "Acme Corp")
        gh.add(1, "first", RECENT)
        gh.add(2, "flaky", RECENT)
        gh.add(3, "third", RECENT)
        gh.failing_details.add(2)

        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        # 1 of 3 details failed: the others are stored, the source is fine.
        assert [r.external_key for r in await vacancies(db)] == [
            "gh:acme/1",
            "gh:acme/3",
        ]
        assert set(await seen_keys(db)) == {"gh:acme/1", "gh:acme/3"}
        source = await get_source(db, source_id)
        assert source.initial_scan_completed_at == NOW
        assert source.last_error is None
        assert source.failing_since is None

        # The next run retries the skipped job (its key was not recorded).
        gh.failing_details.clear()
        gh.detail_requests.clear()
        await check_all(factory, http, ai, at(LATER), config=CONFIG, sleep=sleep)

        assert gh.detail_requests == [2]
        assert "gh:acme/2" in await seen_keys(db)
        assert len(await vacancies(db)) == 3

    @pytest.mark.parametrize("failing", [{1}, {1, 2}, {1, 2, 3}])
    async def test_most_job_details_failing_makes_the_board_unreachable(
        self, factory, db, gh, http, ai, sleep, failing
    ) -> None:
        user_id = await make_user(db, description=None)
        source_id = await make_board(db, user_id, "greenhouse", "acme", "Acme Corp")
        for job_id in range(1, 4 if len(failing) > 1 else 2):
            gh.add(job_id, f"job {job_id}", RECENT)
        gh.add(10, "old job", OLD)
        gh.failing_details.update(failing)

        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        # More than half failed: an outage, so nothing at all is stored
        # (not even the seen-only key of the old job).
        source = await get_source(db, source_id)
        assert source.last_error == "Could not reach the source"
        assert source.failing_since == NOW
        assert source.initial_scan_completed_at is None
        assert await seen_keys(db) == {}
        assert await vacancies(db) == []

    async def test_closed_jobs_do_not_count_as_detail_failures(
        self, factory, db, gh, http, ai, sleep
    ) -> None:
        user_id = await make_user(db, description=None)
        source_id = await make_board(db, user_id, "greenhouse", "acme", "Acme Corp")
        for job_id in range(1, 5):
            gh.add(job_id, f"job {job_id}", RECENT)
        gh.missing_details.update({1, 2, 3})  # closed meanwhile (404)

        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        assert [r.external_key for r in await vacancies(db)] == ["gh:acme/4"]
        source = await get_source(db, source_id)
        assert source.last_error is None
        assert source.initial_scan_completed_at == NOW

    async def test_failing_listing_still_fails_the_source_on_hourly_check(
        self, factory, db, gh, http, ai, sleep
    ) -> None:
        user_id = await make_user(db, description=None)
        source_id = await make_board(db, user_id, "greenhouse", "acme", "Acme Corp")
        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        gh.fail_list = 503
        gh.add(1, "new job", LATER)
        await check_all(factory, http, ai, at(LATER), config=CONFIG, sleep=sleep)

        source = await get_source(db, source_id)
        assert source.last_error == "Could not reach the source"
        assert source.failing_since == LATER
        assert gh.detail_requests == []


# --- Lever ---------------------------------------------------------------------------


class TestLever:
    async def test_initial_scan_pages_through_the_whole_board(
        self, factory, db, lever_board, http, ai, sleep
    ) -> None:
        user_id = await make_user(db, description=None)
        source_id = await make_board(db, user_id, "lever", "acme-labs", "Acme Labs")
        for n in range(120):
            created = RECENT if n % 40 == 0 else OLD if n % 2 else None
            lever_board.add(f"p{n:03d}", f"posting {n}", created, title=f"Role {n}")

        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        assert lever_board.requests == [(0, 50), (50, 50), (100, 50)]
        keys = await seen_keys(db)
        assert len(keys) == 120
        assert "lever:acme-labs/p119" in keys
        rows = await vacancies(db)
        assert [r.external_key for r in rows] == [
            "lever:acme-labs/p000",
            "lever:acme-labs/p040",
            "lever:acme-labs/p080",
        ]
        assert {r.company for r in rows} == {"Acme Labs"}
        assert rows[0].title == "Role 0"
        assert rows[0].job_link == "https://jobs.lever.co/acme-labs/p000"
        assert (
            await card_sources(db)
            == [(source_id, "lever", "acme-labs", "Acme Labs")] * 3
        )

    async def test_hourly_check_on_eu_board(
        self, factory, db, respx_mock, http, ai, sleep
    ) -> None:
        board = LeverBoard(kind="lever_eu", company="acme")
        board.mount(respx_mock)
        user_id = await make_user(db, description=None)
        await make_board(db, user_id, "lever_eu", "acme", "Acme")
        board.add("a", "old posting", OLD)
        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)
        assert await vacancies(db) == []

        board.add("b", "fresh posting", LATER)
        await check_all(factory, http, ai, at(LATER), config=CONFIG, sleep=sleep)

        [row] = await vacancies(db)
        assert row.external_key == "lever_eu:acme/b"
        assert row.url == "https://jobs.eu.lever.co/acme/b"
        assert set(await seen_keys(db)) == {"lever_eu:acme/a", "lever_eu:acme/b"}

    async def test_initial_scan_keeps_seven_days_then_hourly_finds_only_new(
        self, factory, db, tt_board, http, ai, sleep
    ) -> None:
        user_id = await make_user(db, description=None)
        source_id = await make_board(db, user_id, "teamtailor", "acme", "Acme AB")
        tt_board.add(1, "recent job", RECENT, title="Frontend Engineer")
        tt_board.add(2, "old job", OLD)
        tt_board.add(3, "undated job", None)
        tt_board.add(4, "just inside", NOW - timedelta(days=7) + timedelta(minutes=1))

        report = await run_initial_scans(
            factory, http, ai, at(NOW), config=CONFIG, sleep=sleep
        )

        assert tt_board.requests == 1
        assert set(await seen_keys(db)) == {
            "tt:acme/1",
            "tt:acme/2",
            "tt:acme/3",
            "tt:acme/4",
        }
        rows = await vacancies(db)
        assert [r.external_key for r in rows] == ["tt:acme/1", "tt:acme/4"]
        first = rows[0]
        assert first.state == "pending"
        assert first.from_initial_scan is True
        assert first.title == "Frontend Engineer"
        assert first.company == "Acme AB"
        assert first.text == "recent job"
        assert first.posted_at == RECENT
        assert first.job_link == "https://acme.teamtailor.com/jobs/1-dev"
        assert (
            await card_sources(db) == [(source_id, "teamtailor", "acme", "Acme AB")] * 2
        )
        source = await get_source(db, source_id)
        assert source.initial_scan_completed_at == NOW
        assert source.failing_since is None
        assert report.posts_stored == 2
        assert ai.calls == []

        # Hourly: old jobs stay seen-only; only the newly listed one is stored.
        tt_board.add(5, "brand new", None)
        await check_all(factory, http, ai, at(LATER), config=CONFIG, sleep=sleep)

        rows = {r.external_key: r for r in await vacancies(db)}
        assert set(rows) == {"tt:acme/1", "tt:acme/4", "tt:acme/5"}
        new = rows["tt:acme/5"]
        assert new.from_initial_scan is False
        assert new.posted_at == LATER  # undated -> check time
        assert "tt:acme/5" in await seen_keys(db)

    async def test_unreadable_feed_is_recorded(
        self, factory, db, tt_board, http, ai, sleep
    ) -> None:
        user_id = await make_user(db, description=None)
        source_id = await make_board(db, user_id, "teamtailor", "acme", "Acme AB")
        tt_board.status = 404

        report = await run_initial_scans(
            factory, http, ai, at(NOW), config=CONFIG, sleep=sleep
        )

        source = await get_source(db, source_id)
        assert source.last_error == "Job board not found"
        assert source.initial_scan_completed_at is None
        assert report.sources_failed == 1
        assert await seen_keys(db) == {}


# --- invariant -------------------------------------------------------------------


async def test_board_paths_make_no_http_call_inside_a_transaction(
    factory: TrackingFactory, db, respx_mock, http, ai, sleep
) -> None:
    open_during_requests: list[int] = []

    def track(request: httpx.Request) -> None:
        open_during_requests.append(factory.open_transactions())

    gh = GreenhouseBoard(on_request=track)
    gh.mount(respx_mock)
    lever_board = LeverBoard(on_request=track)
    lever_board.mount(respx_mock)
    user_id = await make_user(db)
    await make_board(db, user_id, "greenhouse", "acme", "Acme Corp")
    await make_board(db, user_id, "lever", "acme-labs", "Acme Labs")
    for n in range(1, 4):
        gh.add(n, f"MATCH gh {n}", RECENT)
    for n in range(60):
        lever_board.add(f"p{n}", f"MATCH lever {n}", RECENT if n < 2 else OLD)

    await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)
    gh.add(10, "MATCH gh new", LATER)
    lever_board.add("new", "MATCH lever new", LATER)
    await check_all(factory, http, ai, at(LATER), config=CONFIG, sleep=sleep)

    # list + 3 details + 1 new detail (+ lists) on Greenhouse, 2 pages x 2 on Lever.
    assert len(open_during_requests) >= 10
    assert set(open_during_requests) == {0}
    assert ai.violations == 0
    assert len(await vacancies(db)) == 7
