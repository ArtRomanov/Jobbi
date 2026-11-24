"""Web sources in the hourly check: one broken source never stops the run,
sources skipped by the time budget go first next time, and the listing step
asks only about the keys of the pages it read (pre-merge findings, spec 010)."""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.discovery import service
from app.discovery.normalize import normalize_url
from app.models.vacancy import Vacancy
from app.models.vacancy_seen_key import VacancySeenKey
from app.models.vacancy_source import VacancySource
from tests.discovery.test_service import (
    CHANNEL_URL,
    CONFIG,
    NOW,
    Channel,
    at,
    get_source,
    make_source,
    make_user,
    vacancies,
)
from tests.discovery.test_web_service import (
    UNREACHABLE,
    FakeMonotonic,
    by_job,
    check,
    make_web_source,
    mark_seen,
    queue_rows,
)
from tests.discovery.web_stubs import JobPage, Sites, WebSite


@pytest.fixture
def sites(respx_mock: Any) -> Sites:
    return Sites(respx_mock)


@pytest.fixture
def channel(respx_mock: Any) -> Channel:
    stub = Channel()
    respx_mock.get(CHANNEL_URL).mock(side_effect=stub)
    return stub


async def _set_last_checked(
    db: async_sessionmaker[AsyncSession], source_id: str, value: Any
) -> None:
    async with db() as session:
        source = await session.get(VacancySource, source_id)
        assert source is not None
        source.last_checked_at = value
        await session.commit()


# --- 1. one broken source does not stop the run -----------------------------------


@pytest.mark.parametrize("error", [ValueError("Invalid IPv6 URL"), OverflowError()])
async def test_listing_crash_is_a_read_failure_and_the_run_goes_on(
    factory, db, sites, http, ai, sleep, monkeypatch, error: Exception
) -> None:
    bad_site = sites.add(WebSite(name="bad"))
    bad_site.add("x", "MATCH bad")
    good_site = sites.add(WebSite(name="good"))
    good_site.add("a", "MATCH React role")
    bad_user = await make_user(db, email="bad@example.com")
    good_user = await make_user(db, email="good@example.com")
    bad_id = await make_web_source(db, bad_user, bad_site)
    good_id = await make_web_source(db, good_user, good_site)
    real = service.read_listing

    async def poisoned(url: str, *args: Any, **kwargs: Any) -> Any:
        if url == bad_site.url:
            raise error
        return await real(url, *args, **kwargs)

    monkeypatch.setattr(service, "read_listing", poisoned)

    report = await check(factory, http, ai, sleep)

    assert report.sources_failed == 1
    bad = await get_source(db, bad_id)
    assert bad.last_error == UNREACHABLE and bad.failing_since == NOW
    [card] = await vacancies(db)
    assert (card.user_id, card.source_id, card.state) == (good_user, good_id, "new")


async def test_listing_crash_respects_the_revision_guard(
    factory, db, sites, http, ai, sleep, monkeypatch
) -> None:
    site = sites.add(WebSite(name="bad"))
    site.add("x")
    user_id = await make_user(db)
    source_id = await make_web_source(db, user_id, site)

    async def edited_then_crash(*args: Any, **kwargs: Any) -> Any:
        async with db() as session:
            source = await session.get(VacancySource, source_id)
            assert source is not None
            source.revision += 1
            await session.commit()
        raise ValueError("boom")

    monkeypatch.setattr(service, "read_listing", edited_then_crash)

    await check(factory, http, ai, sleep)

    source = await get_source(db, source_id)
    assert source.last_error is None and source.failing_since is None


async def test_job_page_crash_counts_as_a_failed_read_and_the_run_goes_on(
    factory, db, sites, http, ai, sleep, monkeypatch
) -> None:
    bad_site = sites.add(WebSite(name="bad"))
    bad_site.add("listed")
    good_site = sites.add(WebSite(name="good"))
    good_site.add("a", "MATCH React role")
    bad_user = await make_user(db, email="bad@example.com")
    good_user = await make_user(db, email="good@example.com")
    bad_id = await make_web_source(db, bad_user, bad_site)
    await mark_seen(db, bad_user, bad_id, bad_site, "listed")
    await queue_rows(db, bad_user, bad_id, bad_site, ["poison", "fine"])
    bad_site.pages["poison"] = JobPage(text="never read")
    bad_site.pages["fine"] = JobPage(text="MATCH fine")
    await make_web_source(db, good_user, good_site)
    real = service.fetch_job

    async def poisoned(url: str, *args: Any, **kwargs: Any) -> Any:
        if url.endswith("/poison"):
            raise OverflowError("date value out of range")
        return await real(url, *args, **kwargs)

    monkeypatch.setattr(service, "fetch_job", poisoned)

    await check(factory, http, ai, sleep)

    good_cards = [r for r in await vacancies(db) if r.user_id == good_user]
    assert [c.state for c in good_cards] == ["new"]  # evaluated in the same run
    for hour in (1, 2):
        rows = by_job([r for r in await vacancies(db) if r.user_id == bad_user])
        assert rows["poison"].needs_detail
        assert rows["poison"].detail_attempts == hour
        # The rest of this source's detail step waits for the next check.
        assert rows["fine"].needs_detail and rows["fine"].detail_attempts == 0
        await check(factory, http, ai, sleep, NOW + timedelta(hours=hour))

    # Third failure: released and rated by its listing title (no match: dropped).
    assert any(sent.endswith("Listed poison") for sent in ai.posts_sent)
    rows = by_job([r for r in await vacancies(db) if r.user_id == bad_user])
    assert "poison" not in rows
    assert rows["fine"].needs_detail

    await check(factory, http, ai, sleep, NOW + timedelta(hours=3))

    rows = by_job([r for r in await vacancies(db) if r.user_id == bad_user])
    assert rows["fine"].needs_detail is False and rows["fine"].state == "new"


async def test_telegram_source_crash_is_a_read_failure_and_the_run_goes_on(
    factory, db, channel, http, ai, sleep, monkeypatch
) -> None:
    user_id = await make_user(db)
    bad_id = await make_source(db, user_id, handle="bad_channel", scanned=True)
    await make_source(db, user_id, scanned=True)
    channel.add(10, "MATCH")
    real = service.fetch_channel_posts

    async def poisoned(client: Any, handle: str, *args: Any, **kwargs: Any) -> Any:
        if handle == "bad_channel":
            raise OverflowError("bad date")
        return await real(client, handle, *args, **kwargs)

    monkeypatch.setattr(service, "fetch_channel_posts", poisoned)

    report = await service.check_all(
        factory, http, ai, at(NOW), config=CONFIG, sleep=sleep
    )

    assert report.sources_failed == 1
    assert (await get_source(db, bad_id)).last_error == UNREACHABLE
    [card] = await vacancies(db)
    assert card.state == "new"


# --- 6. a title-less row released after 3 failures still has text ---------------


async def test_title_less_row_is_released_with_its_link_as_text(
    factory, db, sites, http, ai, sleep
) -> None:
    site = sites.add(WebSite(name="acme"))
    site.add("listed")
    user_id = await make_user(db)
    source_id = await make_web_source(db, user_id, site)
    await mark_seen(db, user_id, source_id, site, "listed")
    site.listed.append("x")  # no page: answers 500
    await queue_rows(db, user_id, source_id, site, ["x"], detail_attempts=2)
    async with db() as session:
        row = (await session.scalars(select(Vacancy))).one()
        row.title = None
        await session.commit()

    await check(factory, http, ai, sleep)

    # Rated by the AI with the link as its text (the reply drops it: no match).
    [sent] = ai.posts_sent
    assert sent.strip().endswith(normalize_url(site.job_url("x")))


# --- 2. sources skipped by the time budget go first next time --------------------


async def test_listing_order_is_least_recently_checked_first(
    factory, db, sites, http, ai, sleep
) -> None:
    user_id = await make_user(db, description=None)
    clock = FakeMonotonic()

    def slow(request: Any) -> None:
        clock.now += 3000.0  # one listing spends the whole 40-minute budget

    ids: dict[str, str] = {}
    for name in ("first", "older", "never"):
        site = sites.add(WebSite(name=name, on_request=slow))
        site.add("a")
        ids[name] = await make_web_source(db, user_id, site)
    await _set_last_checked(db, ids["older"], NOW - timedelta(days=3))
    await _set_last_checked(db, ids["never"], None)

    await check(factory, http, ai, sleep, monotonic=clock)

    assert [n for n in ("first", "older", "never") if sites.by_name[n].requests] == [
        "never"
    ]

    await check(factory, http, ai, sleep, NOW + timedelta(hours=1), monotonic=clock)

    assert sites.by_name["older"].requests and not sites.by_name["first"].requests


async def test_detail_step_serves_the_source_waiting_longest_first(
    factory, db, sites, http, ai, sleep
) -> None:
    user_id = await make_user(db)
    clock = FakeMonotonic()

    def slow_pages(request: Any) -> None:
        if "/vacancy/" in request.url.path:
            clock.now += 3000.0  # one job page spends the whole budget

    busy = sites.add(WebSite(name="busy", on_request=slow_pages))
    quiet = sites.add(WebSite(name="quiet", on_request=slow_pages))
    busy_id = await make_web_source(db, user_id, busy)
    quiet_id = await make_web_source(db, user_id, quiet)
    quiet.add("q0", "quiet job")
    await mark_seen(db, user_id, quiet_id, quiet, "q0")
    busy.add("b0", "busy job 0")
    await mark_seen(db, user_id, busy_id, busy, "b0")
    await queue_rows(
        db, user_id, busy_id, busy, ["b1"], found_at=NOW - timedelta(hours=2)
    )
    await queue_rows(
        db, user_id, quiet_id, quiet, ["q1"], found_at=NOW - timedelta(hours=1)
    )
    busy.pages["b1"] = JobPage(text="b1")
    quiet.pages["q1"] = JobPage(text="q1")

    await check(factory, http, ai, sleep, monotonic=clock)

    assert busy.job_requests == ["b1"] and quiet.job_requests == []

    # The busy site lists a new job every hour; the quiet row waits longer now.
    busy.listed.insert(0, "b2")
    busy.pages["b2"] = JobPage(text="b2")
    await check(factory, http, ai, sleep, NOW + timedelta(hours=1), monotonic=clock)

    assert quiet.job_requests == ["q1"]
    assert busy.job_requests == ["b1"]


# --- 3. the listing step asks only about the keys of the pages it read -----------


async def test_listing_queries_only_the_keys_of_the_pages_read(
    factory, db, sites, http, ai, sleep
) -> None:
    user_id = await make_user(db, description=None)
    site = sites.add(WebSite(name="acme"))
    for job_id in "abcd":
        site.add(job_id)
    source_id = await make_web_source(db, user_id, site)
    await mark_seen(db, user_id, source_id, site, "c")
    async with db() as session:
        session.add_all(
            VacancySeenKey(
                user_id=user_id,
                external_key=f"web:{source_id}/{n:064x}",
                first_seen_at=NOW - timedelta(days=30),
            )
            for n in range(10_000)
        )
        await session.commit()
    statements: list[tuple[str, Any]] = []
    engine = factory.maker.kw["bind"].sync_engine

    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        if "vacancy_seen_keys" in statement and statement.lstrip().upper().startswith(
            "SELECT"
        ):
            statements.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", record)
    try:
        await check(factory, http, ai, sleep)
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert site.listing_requests == [1, 2]  # stopped after the page holding "c"
    assert sorted(by_job(await vacancies(db))) == ["a", "b", "d"]
    assert statements, "the seen keys of each page are looked up"
    assert not any("LIKE" in sql.upper() for sql, _ in statements)
    # Each lookup binds the user id plus listed keys only (2 per page, 4 read),
    # never the 10 000 keys of the source's history.
    assert all(len(params) <= 1 + 4 for _, params in statements)
