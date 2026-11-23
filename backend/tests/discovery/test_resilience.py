"""Slice 8: first-scan backoff, retention (`cleanup`) and repost merge.

Same harness as `test_service.py`: file-backed SQLite, respx Telegram/board
stubs, a fake Groq and fixed clocks.
"""

from datetime import datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.discovery.service import (
    CARD_RETENTION,
    PENDING_WITHOUT_DESCRIPTION_RETENTION,
    _next_initial_attempt,
    check_all,
    cleanup,
    run_initial_scans,
)
from app.models.application import Application
from app.models.vacancy import Vacancy, VacancyCardSource
from app.models.vacancy_seen_key import VacancySeenKey
from app.models.vacancy_source import VacancySource
from app.services.vacancy_source_service import is_unavailable
from tests.discovery.board_stubs import GreenhouseBoard
from tests.discovery.fake_bot import FakeBot
from tests.discovery.test_service import (
    CHANNEL,
    CHANNEL_URL,
    CONFIG,
    NOW,
    Channel,
    TrackingFactory,
    at,
    get_source,
    link_telegram,
    make_source,
    make_user,
    seen_keys,
    set_description,
    vacancies,
)

SECOND = "second_channel"
JOB = "https://jobs.example.com/frontend-1"


@pytest.fixture
def bot(factory: TrackingFactory) -> FakeBot:
    return FakeBot(open_transactions=factory.open_transactions)


def with_link(text: str, href: str = JOB) -> str:
    return f'{text} <a href="{href}">Apply</a>'


async def card_sources(
    db: async_sessionmaker[AsyncSession],
) -> dict[str, list[str]]:
    """vacancy_id → source handles (sorted)."""
    async with db() as session:
        rows = await session.execute(
            select(VacancyCardSource.vacancy_id, VacancyCardSource.source_handle)
        )
        result: dict[str, list[str]] = {}
        for vacancy_id, handle in rows:
            result.setdefault(vacancy_id, []).append(handle)
        return {key: sorted(handles) for key, handles in result.items()}


# --- first-scan backoff ------------------------------------------------------------


@pytest.mark.parametrize(
    ("since_first_failure", "retry_after"),
    [
        (None, timedelta(minutes=1)),  # 1st failure (failing_since not set yet)
        (timedelta(0), timedelta(minutes=1)),
        (timedelta(minutes=1), timedelta(minutes=5)),  # 2nd
        (timedelta(minutes=5, seconds=59), timedelta(minutes=5)),
        (timedelta(minutes=6), timedelta(minutes=15)),  # 3rd
        (timedelta(minutes=21), timedelta(hours=1)),  # 4th and later
        (timedelta(hours=20), timedelta(hours=1)),
    ],
)
def test_next_initial_attempt_schedule(
    since_first_failure: timedelta | None, retry_after: timedelta
) -> None:
    failing_since = None if since_first_failure is None else NOW - since_first_failure
    assert _next_initial_attempt(NOW, failing_since) == NOW + retry_after


class TestInitialBackoff:
    async def test_failing_first_scan_retries_at_1_5_15_min_then_hourly(
        self, factory, db, respx_mock, http, ai, sleep
    ) -> None:
        route = respx_mock.get(CHANNEL_URL).mock(return_value=httpx.Response(500))
        user_id = await make_user(db)
        source_id = await make_source(db, user_id)

        async def run(minute: float) -> None:
            moment = NOW + timedelta(minutes=minute)
            await run_initial_scans(
                factory, http, ai, at(moment), config=CONFIG, sleep=sleep
            )

        # (run at minute, fetched?, next attempt at minute)
        timeline = [
            (0, True, 1),
            (0.5, False, 1),
            (1, True, 6),
            (5, False, 6),
            (6, True, 21),
            (20, False, 21),
            (21, True, 81),
            (80, False, 81),
            (81, True, 141),
        ]
        calls = 0
        for minute, fetched, next_minute in timeline:
            await run(minute)
            calls += fetched
            assert route.call_count == calls, minute
            source = await get_source(db, source_id)
            assert source.next_initial_attempt_at == NOW + timedelta(
                minutes=next_minute
            ), minute
            assert source.failing_since == NOW
            assert source.initial_scan_completed_at is None

    async def test_success_clears_backoff_and_error(
        self, factory, db, http, ai, sleep, respx_mock
    ) -> None:
        stub = Channel()
        stub.add(10, "MATCH")
        respx_mock.get(CHANNEL_URL).mock(side_effect=stub)
        user_id = await make_user(db, description=None)
        source_id = await make_source(db, user_id)
        async with db() as session:
            source = await session.get(VacancySource, source_id)
            source.failing_since = NOW - timedelta(hours=3)
            source.last_error = "Could not reach the source"
            source.next_initial_attempt_at = NOW
            await session.commit()

        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        source = await get_source(db, source_id)
        assert source.next_initial_attempt_at is None
        assert (source.failing_since, source.last_error) == (None, None)
        assert source.initial_scan_completed_at == NOW
        assert len(await vacancies(db)) == 1

    async def test_failing_first_scan_becomes_unavailable_after_24_hours(
        self, factory, db, respx_mock, http, ai, sleep
    ) -> None:
        route = respx_mock.get(CHANNEL_URL).mock(
            return_value=httpx.Response(302, headers={"Location": "https://t.me/x"})
        )
        user_id = await make_user(db)
        source_id = await make_source(db, user_id)

        # The worker runs every minute; only due sources are fetched.
        moment = NOW
        states: list[tuple[datetime, bool]] = []
        while moment <= NOW + timedelta(hours=25):
            await run_initial_scans(
                factory, http, ai, at(moment), config=CONFIG, sleep=sleep
            )
            source = await get_source(db, source_id)
            states.append((moment, is_unavailable(source, moment)))
            assert source.next_initial_attempt_at is not None
            moment = source.next_initial_attempt_at

        source = await get_source(db, source_id)
        assert source.last_error == "Channel is private or deleted"
        assert source.initial_scan_completed_at is None
        # 1, 5, 15 min, then hourly: 3 + ~24 retries in 25 h, not ~1 500.
        assert 26 <= route.call_count <= 29
        assert not is_unavailable(source, NOW + timedelta(hours=23, minutes=59))
        assert is_unavailable(source, NOW + timedelta(hours=24))
        assert [unavailable for _, unavailable in states] == [
            moment - NOW >= timedelta(hours=24) for moment, _ in states
        ]


# --- retention ---------------------------------------------------------------------


async def add_card(
    db: async_sessionmaker[AsyncSession],
    user_id: str,
    key: str,
    *,
    state: str,
    found_at: datetime,
    job_link: str | None = None,
    with_application: bool = True,
) -> str:
    """Insert a card with one card source. An `added` card is linked to a new
    application unless `with_application` is False (application deleted)."""
    async with db() as session:
        session.add(
            VacancySeenKey(user_id=user_id, external_key=key, first_seen_at=found_at)
        )
        application_id = None
        if state == "added" and with_application:
            application = Application(
                user_id=user_id, company_name="Acme", role_title="Dev"
            )
            session.add(application)
            await session.flush()
            application_id = application.id
        card = Vacancy(
            user_id=user_id,
            external_key=key,
            url=f"https://t.me/{key}",
            job_link=job_link,
            text="MATCH",
            posted_at=found_at,
            found_at=found_at,
            state=state,
            fit=None if state == "pending" else "high",
            application_id=application_id,
        )
        session.add(card)
        await session.flush()
        session.add(
            VacancyCardSource(
                vacancy_id=card.id,
                source_kind="telegram",
                source_handle=CHANNEL,
                label=f"@{CHANNEL}",
            )
        )
        await session.commit()
        return card.id


DAY = timedelta(days=1)


class TestCleanup:
    @pytest.mark.parametrize(
        ("state", "description", "age", "deleted"),
        [
            # Cards: 30 days after they were first fetched, whatever the user.
            ("new", "desc", CARD_RETENTION + timedelta(minutes=1), True),
            ("seen", "desc", CARD_RETENTION + DAY, True),
            ("dismissed", None, CARD_RETENTION + DAY, True),
            ("new", "desc", CARD_RETENTION - timedelta(minutes=1), False),
            ("seen", None, CARD_RETENTION - DAY, False),
            ("dismissed", "desc", CARD_RETENTION - DAY, False),
            # Added cards live on as the link to their application.
            ("added", "desc", CARD_RETENTION * 3, False),
            ("added", None, CARD_RETENTION * 3, False),
            # Pending: dropped after 7 days only without a description.
            ("pending", None, PENDING_WITHOUT_DESCRIPTION_RETENTION + DAY, True),
            ("pending", "   ", PENDING_WITHOUT_DESCRIPTION_RETENTION + DAY, True),
            ("pending", None, PENDING_WITHOUT_DESCRIPTION_RETENTION - DAY, False),
            # Waiting for the AI or the daily cap: never dropped.
            ("pending", "desc", PENDING_WITHOUT_DESCRIPTION_RETENTION + DAY, False),
            ("pending", "desc", CARD_RETENTION * 2, False),
        ],
    )
    async def test_rules(self, factory, db, state, description, age, deleted) -> None:
        user_id = await make_user(db, description=description)
        card_id = await add_card(db, user_id, "tg:c/1", state=state, found_at=NOW - age)

        report = await cleanup(factory, at(NOW))

        assert [c.id for c in await vacancies(db)] == ([] if deleted else [card_id])
        assert await card_sources(db) == ({} if deleted else {card_id: [CHANNEL]})
        assert report.cards_deleted + report.pending_deleted == int(deleted)
        assert report.card_sources_deleted == int(deleted)
        # Seen keys are never deleted, so the post never comes back.
        assert list(await seen_keys(db)) == ["tg:c/1"]
        assert factory.open_transactions() == 0

    async def test_only_old_rows_of_each_user_go(self, factory, db) -> None:
        with_desc = await make_user(db)
        without = await make_user(db, description=None, email="u2@example.com")
        old, fresh = NOW - CARD_RETENTION - DAY, NOW - DAY
        keep = {
            await add_card(db, with_desc, "tg:c/1", state="new", found_at=fresh),
            await add_card(db, with_desc, "tg:c/2", state="added", found_at=old),
            await add_card(db, with_desc, "tg:c/3", state="pending", found_at=old),
            await add_card(db, without, "tg:c/4", state="pending", found_at=fresh),
        }
        await add_card(db, with_desc, "tg:c/5", state="dismissed", found_at=old)
        await add_card(db, without, "tg:c/6", state="seen", found_at=old)
        await add_card(db, without, "tg:c/7", state="pending", found_at=old)

        report = await cleanup(factory, at(NOW))

        assert {c.id for c in await vacancies(db)} == keep
        assert set(await card_sources(db)) == keep
        assert (report.cards_deleted, report.pending_deleted) == (2, 1)
        assert len(await seen_keys(db)) == 7

    async def test_added_card_whose_application_was_deleted_goes(
        self, factory, db
    ) -> None:
        """Deleting an application clears the card's link; cleanup then drops
        the card and its sources whatever its age. Its seen key stays."""
        user_id = await make_user(db)
        orphan = await add_card(
            db, user_id, "tg:c/1", state="added", found_at=NOW, with_application=False
        )
        linked = await add_card(db, user_id, "tg:c/2", state="added", found_at=NOW)

        report = await cleanup(factory, at(NOW))

        assert [c.id for c in await vacancies(db)] == [linked]
        assert await card_sources(db) == {linked: [CHANNEL]}
        assert report.cards_deleted == 1
        assert report.card_sources_deleted == 1
        assert orphan not in {c.id for c in await vacancies(db)}
        assert set(await seen_keys(db)) == {"tg:c/1", "tg:c/2"}

    async def test_deleted_dismissed_card_never_reappears_while_board_lists_job(
        self, factory, db, respx_mock, http, ai, sleep
    ) -> None:
        board = GreenhouseBoard()
        board.mount(respx_mock)
        start = NOW - CARD_RETENTION - DAY
        board.add(1, "MATCH job", start - DAY)
        user_id = await make_user(db)
        async with db() as session:
            session.add(
                VacancySource(
                    user_id=user_id,
                    kind="greenhouse",
                    handle=board.token,
                    default_name=board.name,
                    display_name=board.name,
                )
            )
            await session.commit()
        await run_initial_scans(
            factory, http, ai, at(start), config=CONFIG, sleep=sleep
        )
        [card] = await vacancies(db)
        assert card.state == "new"
        async with db() as session:
            row = await session.get(Vacancy, card.id)
            row.state = "dismissed"
            await session.commit()

        report = await cleanup(factory, at(NOW))
        await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        assert report.cards_deleted == 1
        assert await vacancies(db) == []
        assert await card_sources(db) == {}
        assert board.detail_requests == [1]  # never fetched again
        assert len(ai.calls) == 1


# --- repost merge ------------------------------------------------------------------


@pytest.fixture
def channels(respx_mock: respx.MockRouter) -> tuple[Channel, Channel]:
    first, second = Channel(), Channel(name=SECOND)
    respx_mock.get(CHANNEL_URL).mock(side_effect=first)
    respx_mock.get(f"https://t.me/s/{SECOND}").mock(side_effect=second)
    return first, second


async def two_sources(db: async_sessionmaker[AsyncSession]) -> str:
    user_id = await make_user(db)
    await make_source(db, user_id, scanned=True)
    await make_source(db, user_id, handle=SECOND, scanned=True)
    return user_id


async def set_state(
    db: async_sessionmaker[AsyncSession], vacancy_id: str, state: str
) -> None:
    async with db() as session:
        row = await session.get(Vacancy, vacancy_id)
        assert row is not None
        row.state = state
        await session.commit()


class TestRepostMerge:
    async def test_same_job_link_in_two_channels_in_one_run_is_one_card(
        self, factory, db, channels, http, ai, sleep, bot
    ) -> None:
        first, second = channels
        user_id = await two_sources(db)
        await link_telegram(db, user_id)
        first.add(10, with_link("MATCH HIGH first"), NOW - timedelta(hours=3))
        second.add(20, with_link("MATCH LOW repost"), NOW - timedelta(hours=1))

        report = await check_all(
            factory, http, ai, at(NOW), config=CONFIG, sleep=sleep, bot=bot
        )

        [card] = await vacancies(db)
        # The card keeps the date, fit and text of the first post.
        assert card.external_key == f"tg:{CHANNEL}/10"
        assert card.posted_at == NOW - timedelta(hours=3)
        assert card.fit == "high"
        assert card.text.startswith("MATCH HIGH first")
        assert card.job_link == JOB
        assert await card_sources(db) == {card.id: sorted([CHANNEL, SECOND])}
        # Both keys remembered, so neither post ever comes back.
        assert set(await seen_keys(db)) == {f"tg:{CHANNEL}/10", f"tg:{SECOND}/20"}
        assert report.posts_merged == 1
        assert report.new_card_ids == {user_id: [card.id]}
        # The alert counts the card once.
        assert [text.splitlines()[0] for text in bot.texts] == ["🔎 1 new vacancy"]
        assert ai.violations == 0 and bot.violations == 0

    async def test_repost_of_existing_card_merges_without_ai_call(
        self, factory, db, channels, http, ai, sleep, bot
    ) -> None:
        first, second = channels
        user_id = await two_sources(db)
        await link_telegram(db, user_id)
        first.add(10, with_link("MATCH first"), NOW - timedelta(hours=2))
        await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)
        [card] = await vacancies(db)
        calls_before = len(ai.calls)

        second.add(20, with_link("MATCH repost"), NOW + timedelta(minutes=30))
        report = await check_all(
            factory,
            http,
            ai,
            at(NOW + timedelta(hours=1)),
            config=CONFIG,
            sleep=sleep,
            bot=bot,
        )

        assert [c.id for c in await vacancies(db)] == [card.id]
        assert await card_sources(db) == {card.id: sorted([CHANNEL, SECOND])}
        assert len(ai.calls) == calls_before  # no AI call for the repost
        assert report.posts_merged == 1 and report.posts_stored == 0
        assert bot.sent == []  # nothing new to announce
        assert f"tg:{SECOND}/20" in await seen_keys(db)

    @pytest.mark.parametrize("state", ["seen", "dismissed"])
    async def test_merged_card_keeps_its_state(
        self, factory, db, channels, http, ai, sleep, state
    ) -> None:
        first, second = channels
        await two_sources(db)
        first.add(10, with_link("MATCH first"), NOW - timedelta(hours=2))
        await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)
        [card] = await vacancies(db)
        await set_state(db, card.id, state)

        second.add(20, with_link("MATCH repost"), NOW + timedelta(minutes=30))
        await check_all(
            factory, http, ai, at(NOW + timedelta(hours=1)), config=CONFIG, sleep=sleep
        )

        [merged] = await vacancies(db)
        assert (merged.id, merged.state) == (card.id, state)
        assert await card_sources(db) == {card.id: sorted([CHANNEL, SECOND])}

    async def test_pending_repost_merges_into_card_rated_later(
        self, factory, db, channels, http, ai, sleep
    ) -> None:
        """Both posts wait (no description); once rated, the second merges."""
        first, second = channels
        user_id = await make_user(db, description=None)
        await make_source(db, user_id, scanned=True)
        await make_source(db, user_id, handle=SECOND, scanned=True)
        first.add(10, with_link("MATCH first"), NOW - timedelta(hours=2))
        await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)
        second.add(20, with_link("MATCH repost"), NOW + timedelta(minutes=10))
        later = NOW + timedelta(hours=1)
        await check_all(factory, http, ai, at(later), config=CONFIG, sleep=sleep)
        assert [c.state for c in await vacancies(db)] == ["pending", "pending"]

        await set_description(db, user_id, "Frontend")
        report = await check_all(
            factory,
            http,
            ai,
            at(later + timedelta(hours=1)),
            config=CONFIG,
            sleep=sleep,
        )

        [card] = await vacancies(db)
        assert card.external_key == f"tg:{CHANNEL}/10"
        assert await card_sources(db) == {card.id: sorted([CHANNEL, SECOND])}
        assert report.new_card_ids == {user_id: [card.id]}
        assert report.posts_merged == 1

    @pytest.mark.parametrize("user_state", ["new", "seen", "dismissed"])
    async def test_first_post_rated_late_takes_over_the_later_card(
        self, factory, db, channels, http, ai, sleep, bot, user_state
    ) -> None:
        """Cold-round probe: P is found first but left out of the AI answer;
        Q (same job, found later) becomes the card; when P is finally rated,
        the card keeps P's key, date, fit and text (spec 2.2), the user's
        state on Q, both sources, and Q's alert is not repeated."""
        first, second = channels
        user_id = await two_sources(db)
        await link_telegram(db, user_id)
        first.add(10, with_link("MATCH HIGH first SKIP"), NOW - timedelta(hours=3))
        await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)
        [p_row] = await vacancies(db)
        assert p_row.state == "pending"

        second.add(20, with_link("MATCH LOW repost"), NOW + timedelta(minutes=30))
        run2 = NOW + timedelta(hours=1)
        await check_all(
            factory, http, ai, at(run2), config=CONFIG, sleep=sleep, bot=bot
        )
        states = {c.external_key: c.state for c in await vacancies(db)}
        assert states == {f"tg:{CHANNEL}/10": "pending", f"tg:{SECOND}/20": "new"}
        q_id = next(c.id for c in await vacancies(db) if c.state == "new")
        await set_state(db, q_id, user_state)
        assert len(bot.texts) == 1
        # The AI answers P this time.
        async with db() as session:
            row = await session.get(Vacancy, p_row.id)
            row.text = "MATCH HIGH first"
            await session.commit()

        report = await check_all(
            factory,
            http,
            ai,
            at(run2 + timedelta(hours=1)),
            config=CONFIG,
            sleep=sleep,
            bot=bot,
        )

        [card] = await vacancies(db)
        assert card.id == p_row.id
        assert card.external_key == f"tg:{CHANNEL}/10"
        assert card.posted_at == NOW - timedelta(hours=3)
        assert card.found_at == NOW
        assert (card.fit, card.text) == ("high", "MATCH HIGH first")
        assert card.state == user_state
        assert card.alert_handled_at is not None
        assert await card_sources(db) == {card.id: sorted([CHANNEL, SECOND])}
        assert set(await seen_keys(db)) == {f"tg:{CHANNEL}/10", f"tg:{SECOND}/20"}
        assert report.posts_merged == 1
        assert len(bot.texts) == 1  # Q's alert is not repeated
        assert ai.violations == 0 and bot.violations == 0

    async def test_posts_without_external_link_never_merge(
        self, factory, db, channels, http, ai, sleep
    ) -> None:
        first, second = channels
        await two_sources(db)
        # Same text, only Telegram links: job_link stays empty.
        tg_only = f'MATCH same job <a href="https://t.me/{CHANNEL}/1">ref</a>'
        first.add(10, tg_only)
        second.add(20, tg_only)

        report = await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        cards = await vacancies(db)
        assert [(c.state, c.job_link) for c in cards] == [("new", None)] * 2
        assert report.posts_merged == 0
        assert len(await card_sources(db)) == 2

    async def test_added_card_is_not_a_merge_target(
        self, factory, db, channels, http, ai, sleep
    ) -> None:
        first, _ = channels
        user_id = await two_sources(db)
        added_id = await add_card(
            db,
            user_id,
            "tg:old/1",
            state="added",
            found_at=NOW - DAY,
            job_link=JOB,
        )
        first.add(10, with_link("MATCH new post"))

        report = await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

        cards = {c.id: c.state for c in await vacancies(db)}
        assert cards.pop(added_id) == "added"
        assert list(cards.values()) == ["new"]
        assert report.posts_merged == 0

    async def test_same_channel_twice_lists_the_source_once(
        self, factory, db, channels, http, ai, sleep
    ) -> None:
        first, _ = channels
        await two_sources(db)
        first.add(10, with_link("MATCH first"), NOW - timedelta(hours=2))
        await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)
        first.add(11, with_link("MATCH bumped again"), NOW + timedelta(minutes=5))

        await check_all(
            factory, http, ai, at(NOW + timedelta(hours=1)), config=CONFIG, sleep=sleep
        )

        [card] = await vacancies(db)
        assert await card_sources(db) == {card.id: [CHANNEL]}

    async def test_telegram_repost_of_board_job_joins_the_board_card(
        self, factory, db, respx_mock, http, ai, sleep
    ) -> None:
        board = GreenhouseBoard()
        board.mount(respx_mock)
        board.add(1, "MATCH board job", NOW - DAY)
        stub = Channel()
        respx_mock.get(CHANNEL_URL).mock(side_effect=stub)
        user_id = await make_user(db)
        await make_source(db, user_id, scanned=True)
        async with db() as session:
            session.add(
                VacancySource(
                    user_id=user_id,
                    kind="greenhouse",
                    handle=board.token,
                    default_name=board.name,
                    display_name=board.name,
                )
            )
            await session.commit()
        await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)
        [card] = await vacancies(db)
        link = f"https://job-boards.greenhouse.io/{board.token}/jobs/1?utm_source=tg"
        stub.add(10, with_link("MATCH we are hiring", link), NOW + timedelta(minutes=5))

        await check_all(
            factory, http, ai, at(NOW + timedelta(hours=1)), config=CONFIG, sleep=sleep
        )

        assert [c.id for c in await vacancies(db)] == [card.id]
        assert await card_sources(db) == {card.id: sorted([CHANNEL, board.token])}


# --- invariant: no network I/O inside a transaction --------------------------------


async def test_merge_backoff_and_cleanup_open_no_transaction_during_network(
    factory, db, respx_mock, http, ai, sleep, bot
) -> None:
    violations: list[int] = []
    first, second = Channel(), Channel(name=SECOND)
    for stub, url in ((first, CHANNEL_URL), (second, f"https://t.me/s/{SECOND}")):
        stub.on_request = lambda: violations.append(factory.open_transactions())
        respx_mock.get(url).mock(side_effect=stub)
    respx_mock.get("https://t.me/s/broken").mock(
        side_effect=lambda request: (
            violations.append(factory.open_transactions()) or httpx.Response(500)
        )
    )
    user_id = await two_sources(db)
    await link_telegram(db, user_id)
    await make_source(db, user_id, handle="broken")
    first.add(10, with_link("MATCH first"), NOW - timedelta(hours=2))
    second.add(20, with_link("MATCH repost"), NOW - timedelta(hours=1))

    await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)
    await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep, bot=bot)
    second.add(21, with_link("MATCH again"), NOW + timedelta(minutes=5))
    await check_all(
        factory,
        http,
        ai,
        at(NOW + timedelta(hours=1)),
        config=CONFIG,
        sleep=sleep,
        bot=bot,
    )
    await cleanup(factory, at(NOW + CARD_RETENTION + DAY))

    assert len(violations) >= 4 and set(violations) == {0}
    assert ai.calls and ai.violations == 0
    assert len(bot.sent) == 1 and bot.violations == 0
    assert factory.open_transactions() == 0
    assert await vacancies(db) == []
