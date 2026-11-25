"""Hourly check of `web` sources: listing step, detail step, evaluation
(respx + stub resolver, fixed clock, file-backed SQLite, fake Groq)."""

from datetime import datetime, timedelta
from typing import Any

import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.discovery import service
from app.discovery.normalize import normalize_url
from app.discovery.service import check_all, evaluate_pending
from app.models.vacancy import Vacancy, VacancyCardSource
from app.models.vacancy_seen_key import VacancySeenKey
from app.models.vacancy_source import VacancySource
from app.services.vacancy_source_service import is_unavailable
from tests.discovery.test_service import (
    CONFIG,
    NOW,
    at,
    get_source,
    make_user,
    seen_keys,
    vacancies,
)
from tests.discovery.web_stubs import JobPage, Sites, WebSite, resolve

WATCHING_SINCE = NOW - timedelta(days=1)
UNREACHABLE = "Could not reach the source"
BLOCKED = "This site blocks automated readers"
NO_VACANCIES = "No vacancies found — check the link or the 'Job link contains' field"


# --- helpers -----------------------------------------------------------------------


@pytest.fixture
def sites(respx_mock: respx.MockRouter) -> Sites:
    return Sites(respx_mock)


@pytest.fixture
def site(sites: Sites) -> WebSite:
    return sites.add(WebSite())


async def make_web_source(
    db: async_sessionmaker[AsyncSession],
    user_id: str,
    site: WebSite,
    *,
    scanned: bool = True,
) -> str:
    async with db() as session:
        source = VacancySource(
            user_id=user_id,
            kind="web",
            handle="placeholder",
            url=site.url,
            url_hash=f"{site.name:0>64}"[:64],
            default_name=site.name,
            display_name=site.name,
            initial_scan_completed_at=WATCHING_SINCE if scanned else None,
            last_checked_at=WATCHING_SINCE,
        )
        session.add(source)
        await session.flush()
        source.handle = source.id
        await session.commit()
        return source.id


async def mark_seen(
    db: async_sessionmaker[AsyncSession],
    user_id: str,
    source_id: str,
    site: WebSite,
    *job_ids: str,
) -> None:
    async with db() as session:
        for job_id in job_ids:
            session.add(
                VacancySeenKey(
                    user_id=user_id,
                    external_key=site.key(source_id, job_id),
                    first_seen_at=WATCHING_SINCE,
                )
            )
        await session.commit()


async def queue_rows(
    db: async_sessionmaker[AsyncSession],
    user_id: str,
    source_id: str,
    site: WebSite,
    job_ids: list[str],
    *,
    found_at: datetime = NOW - timedelta(hours=1),
    detail_attempts: int = 0,
) -> None:
    """`needs_detail` rows queued by an earlier listing (job i found i s later)."""
    async with db() as session:
        for index, job_id in enumerate(job_ids):
            key = site.key(source_id, job_id)
            link = normalize_url(site.job_url(job_id))
            session.add(
                VacancySeenKey(
                    user_id=user_id, external_key=key, first_seen_at=found_at
                )
            )
            vacancy = Vacancy(
                user_id=user_id,
                source_id=source_id,
                external_key=key,
                url=link,
                job_link=link,
                title=f"Listed {job_id}",
                text="",
                posted_at=found_at,
                found_at=found_at + timedelta(seconds=index),
                state="pending",
                needs_detail=True,
                detail_attempts=detail_attempts,
            )
            session.add(vacancy)
            await session.flush()
            session.add(
                VacancyCardSource(
                    vacancy_id=vacancy.id,
                    source_id=source_id,
                    source_kind="web",
                    source_handle=source_id,
                    label=site.name,
                )
            )
        await session.commit()


async def check(
    factory: Any,
    http: Any,
    ai: Any,
    sleep: Any,
    moment: datetime = NOW,
    **kwargs: Any,
) -> service.RunReport:
    return await check_all(
        factory,
        http,
        ai,
        at(moment),
        config=CONFIG,
        sleep=sleep,
        web_resolver=kwargs.pop("web_resolver", resolve),
        **kwargs,
    )


def by_job(rows: list[Vacancy]) -> dict[str, Vacancy]:
    return {row.url.rsplit("/", 1)[1]: row for row in rows}


class FakeMonotonic:
    """A monotonic clock that only moves when a test says so."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# --- full run ----------------------------------------------------------------------


async def test_check_all_lists_reads_job_pages_and_fills_the_inbox(
    factory, db, site, http, ai, sleep
) -> None:
    user_id = await make_user(db)
    source_id = await make_web_source(db, user_id, site)
    posted = datetime(2026, 11, 20, 9, 30)
    site.add(
        "a",
        "MATCH React role at Page Co",
        title="Job a page title",
        company="Page Co",
        posted=posted,
    )
    site.add("b", "Office cleaner wanted")  # no JobPosting; not a match

    report = await check(factory, http, ai, sleep)

    assert site.listing_requests == [1]
    # Rows found in one listing share found_at; their order is not defined.
    assert sorted(site.job_requests) == ["a", "b"]
    assert report.posts_stored == 2 and report.posts_evaluated == 2
    [card] = await vacancies(db)
    assert card.state == "new"
    assert card.needs_detail is False
    # The AI's title and company win for web; the page text and date are kept.
    assert (card.title, card.company) == ("Frontend Developer", "Acme")
    assert card.text == "MATCH React role at Page Co"
    assert card.posted_at == posted
    assert card.found_at == NOW
    assert card.url == card.job_link == normalize_url(site.job_url("a"))
    keys = await seen_keys(db)
    assert set(keys) == {site.key(source_id, "a"), site.key(source_id, "b")}
    assert all(evaluated == NOW for evaluated in keys.values())
    source = await get_source(db, source_id)
    assert source.last_checked_at == NOW and source.last_error is None
    assert report.new_card_ids == {user_id: [card.id]}


# --- listing step ------------------------------------------------------------------


async def test_listing_stops_after_the_page_with_a_seen_job(
    factory, db, site, http, ai, sleep
) -> None:
    user_id = await make_user(db, description=None)
    source_id = await make_web_source(db, user_id, site)
    for job_id in "abcdef":
        site.add(job_id)
    await mark_seen(db, user_id, source_id, site, "d", "e", "f")

    await check(factory, http, ai, sleep)

    assert site.listing_requests == [1, 2]
    rows = await vacancies(db)
    assert sorted(by_job(rows)) == ["a", "b", "c"]
    assert all(row.needs_detail and row.state == "pending" for row in rows)
    assert all(row.text == "" and row.posted_at == NOW for row in rows)
    assert by_job(rows)["a"].title == "Listed a"
    assert sleep.calls == [1.0]  # one pause between the two listing pages


async def test_listing_reads_at_most_five_pages(
    factory, db, site, http, ai, sleep
) -> None:
    user_id = await make_user(db, description=None)
    await make_web_source(db, user_id, site)
    for n in range(12):
        site.add(f"j{n:02d}")

    await check(factory, http, ai, sleep)

    assert site.listing_requests == [1, 2, 3, 4, 5]
    assert len(await vacancies(db)) == 10


async def test_failed_later_page_keeps_the_earlier_pages(
    factory, db, site, http, ai, sleep
) -> None:
    user_id = await make_user(db, description=None)
    source_id = await make_web_source(db, user_id, site)
    for job_id in "abcd":
        site.add(job_id)
    site.failing_pages = {2}

    report = await check(factory, http, ai, sleep)

    assert sorted(by_job(await vacancies(db))) == ["a", "b"]
    assert report.sources_failed == 0
    assert (await get_source(db, source_id)).failing_since is None


async def test_unreadable_first_page_marks_unavailable_after_24_hours_then_recovers(
    factory, db, site, http, ai, sleep
) -> None:
    user_id = await make_user(db, description=None)
    source_id = await make_web_source(db, user_id, site)
    site.add("a")
    site.failing_pages = {1}

    report = await check(factory, http, ai, sleep)
    await check(factory, http, ai, sleep, NOW + timedelta(hours=24))

    assert report.sources_failed == 1
    source = await get_source(db, source_id)
    assert (source.failing_since, source.last_error) == (NOW, UNREACHABLE)
    assert source.last_checked_at == WATCHING_SINCE
    assert not is_unavailable(source, NOW + timedelta(hours=23))
    assert is_unavailable(source, NOW + timedelta(hours=24))
    assert await vacancies(db) == []

    site.failing_pages = set()
    await check(factory, http, ai, sleep, NOW + timedelta(hours=25))

    source = await get_source(db, source_id)
    assert source.failing_since is None and source.last_error is None
    assert len(await vacancies(db)) == 1


async def test_blocked_listing_is_a_read_error_with_the_blocked_reason(
    factory, db, site, http, ai, sleep
) -> None:
    user_id = await make_user(db, description=None)
    source_id = await make_web_source(db, user_id, site)
    site.add("a")
    site.blocked_pages = {1}

    report = await check(factory, http, ai, sleep)
    await check(factory, http, ai, sleep, NOW + timedelta(hours=24))

    assert report.sources_failed == 1
    source = await get_source(db, source_id)
    assert (source.failing_since, source.last_error) == (NOW, BLOCKED)
    assert not is_unavailable(source, NOW + timedelta(hours=23))
    assert is_unavailable(source, NOW + timedelta(hours=24))
    assert await vacancies(db) == []


async def test_listing_without_vacancies_is_a_read_error_until_jobs_appear(
    factory, db, site, http, ai, sleep
) -> None:
    user_id = await make_user(db, description=None)
    source_id = await make_web_source(db, user_id, site)

    for hours in (0, 1, 24):
        await check(factory, http, ai, sleep, NOW + timedelta(hours=hours))

    source = await get_source(db, source_id)
    assert (source.failing_since, source.last_error) == (NOW, NO_VACANCIES)
    assert is_unavailable(source, NOW + timedelta(hours=24))

    site.add("a")
    await check(factory, http, ai, sleep, NOW + timedelta(hours=25))

    source = await get_source(db, source_id)
    assert source.failing_since is None and source.last_error is None
    assert not is_unavailable(source, NOW + timedelta(hours=25))


async def test_host_refused_at_check_time_reads_as_unreachable(
    factory, db, site, http, ai, sleep
) -> None:
    user_id = await make_user(db, description=None)
    source_id = await make_web_source(db, user_id, site)
    site.add("a")

    async def private(host: str, port: int) -> list[str]:
        return ["10.0.0.5"]  # the host now resolves to a private address

    await check(factory, http, ai, sleep, web_resolver=private)

    assert site.requests == []
    assert (await get_source(db, source_id)).last_error == UNREACHABLE


async def test_web_job_merges_by_job_link_into_a_telegram_card(
    factory, db, site, http, ai, sleep
) -> None:
    user_id = await make_user(db)
    source_id = await make_web_source(db, user_id, site)
    site.add("a", "MATCH")
    link = normalize_url(site.job_url("a"))
    async with db() as session:
        card = Vacancy(
            user_id=user_id,
            external_key="tg:jobs/1",
            url="https://t.me/jobs/1",
            job_link=link,
            title="Telegram title",
            text="MATCH from Telegram",
            posted_at=NOW - timedelta(hours=3),
            found_at=NOW - timedelta(hours=3),
            state="new",
            fit="high",
        )
        session.add(card)
        await session.commit()

    report = await check(factory, http, ai, sleep)

    assert report.posts_merged == 1 and report.posts_stored == 0
    assert site.job_requests == [] and ai.calls == []
    [only] = await vacancies(db)
    assert only.id == card.id and only.title == "Telegram title"
    async with db() as session:
        kinds = (
            await session.scalars(
                select(VacancyCardSource.source_kind).where(
                    VacancyCardSource.vacancy_id == card.id
                )
            )
        ).all()
    assert kinds == ["web"]
    assert site.key(source_id, "a") in await seen_keys(db)


# --- detail step -------------------------------------------------------------------


async def test_detail_step_reads_at_most_30_rows_oldest_first(
    factory, db, site, http, ai, sleep
) -> None:
    user_id = await make_user(db)
    source_id = await make_web_source(db, user_id, site)
    site.add("listed")
    await mark_seen(db, user_id, source_id, site, "listed")
    ids = [f"r{n:02d}" for n in range(35)]
    # Queued newest-first by id, so found_at (not insertion order) decides.
    await queue_rows(db, user_id, source_id, site, list(reversed(ids)))
    for job_id in ids:
        site.pages[job_id] = JobPage(text=f"Text {job_id}")

    await check(factory, http, ai, sleep)

    expected = list(reversed(ids))[:30]
    assert site.job_requests == expected
    assert sleep.calls.count(1.0) == 29  # (the AI pause is 30 s)
    rows = by_job(await vacancies(db))
    waiting = {job for job, row in rows.items() if row.needs_detail}
    assert waiting == set(ids[:5])
    # Of the 30 read rows, PER_SOURCE_RUN_LIMIT were rated (and rejected) in
    # this run; the rest wait for the next run (backlog #19).
    assert len(rows) - len(waiting) == 30 - service.PER_SOURCE_RUN_LIMIT
    assert len(ai.posts_sent) == service.PER_SOURCE_RUN_LIMIT
    assert all("Text r" in text for text in ai.posts_sent)


async def test_job_page_retried_and_rated_by_title_after_three_failures(
    factory, db, site, http, ai, sleep
) -> None:
    user_id = await make_user(db)
    source_id = await make_web_source(db, user_id, site)
    await mark_seen(db, user_id, source_id, site, "listed")
    site.add("listed")
    site.listed.append("x")  # listed with no page: answers 500
    await queue_rows(db, user_id, source_id, site, ["x"])
    async with db() as session:
        row = (await session.scalars(select(Vacancy))).one()
        row.title = "MATCH Listed x"
        await session.commit()

    for hours in (0, 1):
        await check(factory, http, ai, sleep, NOW + timedelta(hours=hours))
        [row] = await vacancies(db)
        assert row.needs_detail and row.detail_attempts == hours + 1
    assert ai.calls == []

    await check(factory, http, ai, sleep, NOW + timedelta(hours=2))

    assert site.job_requests == ["x", "x", "x"]
    [card] = await vacancies(db)
    assert card.state == "new" and card.needs_detail is False
    assert card.detail_attempts == 3
    [sent] = ai.posts_sent
    assert sent.endswith("MATCH Listed x")
    assert card.text == "MATCH Listed x"
    assert card.title == "Frontend Developer"


@pytest.mark.parametrize("status", [404, 410])
async def test_gone_job_page_drops_the_row_without_an_ai_call(
    factory, db, site, http, ai, sleep, status: int
) -> None:
    user_id = await make_user(db)
    source_id = await make_web_source(db, user_id, site)
    site.add("a", "MATCH", status=status)

    await check(factory, http, ai, sleep)

    assert site.job_requests == ["a"]
    assert ai.calls == []
    assert await vacancies(db) == []
    assert site.key(source_id, "a") in await seen_keys(db)


async def test_detail_step_runs_when_the_listing_read_failed(
    factory, db, site, http, ai, sleep
) -> None:
    user_id = await make_user(db)
    source_id = await make_web_source(db, user_id, site)
    await queue_rows(db, user_id, source_id, site, ["q"])
    site.pages["q"] = JobPage(text="MATCH queued")
    site.failing_pages = {1}

    report = await check(factory, http, ai, sleep)

    assert report.sources_failed == 1
    assert site.job_requests == ["q"]
    [card] = await vacancies(db)
    assert card.state == "new" and card.text == "MATCH queued"
    assert (await get_source(db, source_id)).last_error == UNREACHABLE


async def test_detail_step_skipped_for_users_without_a_description(
    factory, db, site, http, ai, sleep
) -> None:
    user_id = await make_user(db, description=None)
    await make_web_source(db, user_id, site)
    site.add("a", "MATCH")

    await check(factory, http, ai, sleep)

    assert site.listing_requests == [1] and site.job_requests == []
    [row] = await vacancies(db)
    assert row.needs_detail and row.detail_attempts == 0


async def test_detail_budget_stops_after_three_failures_in_a_row(
    factory, db, site, http, ai, sleep
) -> None:
    user_id = await make_user(db)
    source_id = await make_web_source(db, user_id, site)
    site.add("listed")
    await mark_seen(db, user_id, source_id, site, "listed")
    # r0 reads fine, r1-r3 fail (no page), r4 would read fine.
    await queue_rows(db, user_id, source_id, site, ["r0", "r1", "r2", "r3", "r4"])
    site.pages["r0"] = JobPage(text="r0 text")
    site.pages["r4"] = JobPage(text="r4 text")

    await check(factory, http, ai, sleep)

    assert site.job_requests == ["r0", "r1", "r2", "r3"]
    rows = by_job(await vacancies(db))
    assert [rows[j].detail_attempts for j in ("r1", "r2", "r3")] == [1, 1, 1]
    assert rows["r4"].needs_detail and rows["r4"].detail_attempts == 0

    await check(factory, http, ai, sleep, NOW + timedelta(hours=1))

    assert site.job_requests[4:] == ["r1", "r2", "r3"]


async def test_detail_budget_stops_after_five_minutes_per_source(
    factory, db, site, http, ai, sleep
) -> None:
    user_id = await make_user(db)
    source_id = await make_web_source(db, user_id, site)
    site.add("listed")
    await mark_seen(db, user_id, source_id, site, "listed")
    ids = [f"r{n}" for n in range(6)]
    await queue_rows(db, user_id, source_id, site, ids)
    for job_id in ids:
        site.pages[job_id] = JobPage(text=f"{job_id} text")
    clock = FakeMonotonic()

    def slow(request: Any) -> None:
        if "/vacancy/" in request.url.path:
            clock.now += 100.0  # every job page takes 100 s

    site.on_request = slow

    await check(factory, http, ai, sleep, monotonic=clock)

    assert site.job_requests == ["r0", "r1", "r2"]  # 300 s spent
    rows = by_job(await vacancies(db))
    assert sorted(j for j, row in rows.items() if row.needs_detail) == [
        "r3",
        "r4",
        "r5",
    ]

    site.on_request = None
    await check(factory, http, ai, sleep, NOW + timedelta(hours=1))

    assert site.job_requests[3:] == ["r3", "r4", "r5"]
    assert not any(row.needs_detail for row in await vacancies(db))


async def test_web_part_of_a_check_stops_after_40_minutes(
    factory, db, sites, http, ai, sleep
) -> None:
    user_id = await make_user(db)
    clock = FakeMonotonic()

    def slow(request: Any) -> None:
        clock.now += 1000.0  # every request of these sites takes 1000 s

    names = ["s1", "s2", "s3", "s4"]
    for name in names:
        site = sites.add(WebSite(name=name, on_request=slow))
        site.add("a", "Plain job")
        await make_web_source(db, user_id, site)

    await check(factory, http, ai, sleep, monotonic=clock)

    # Listings at 0, 1000 and 2000 s; the 4th listing and all details wait.
    # (Sources made in the same second are read in id order.)
    assert sorted(bool(sites.by_name[n].requests) for n in names) == [
        False,
        True,
        True,
        True,
    ]
    assert all(not sites.by_name[n].job_requests for n in names)
    rows = await vacancies(db)
    assert len(rows) == 3 and all(row.needs_detail for row in rows)

    for name in names:
        sites.by_name[name].on_request = None
    await check(factory, http, ai, sleep, NOW + timedelta(hours=1))

    assert all(sites.by_name[n].job_requests == ["a"] for n in names)
    assert await vacancies(db) == []  # all read and rated (not a match)


# --- evaluation --------------------------------------------------------------------


async def test_needs_detail_rows_are_not_sent_to_the_ai(
    factory, db, site, http, ai, sleep
) -> None:
    user_id = await make_user(db)
    source_id = await make_web_source(db, user_id, site)
    await queue_rows(db, user_id, source_id, site, ["a"])

    report = await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    assert ai.calls == [] and report.posts_evaluated == 0
    assert await service._users_with_pending(factory, None) == []


@pytest.mark.parametrize(
    ("key", "expected_title", "expected_company"),
    [
        ("web:src/abc", "Frontend Developer", "Acme"),
        ("tg:jobs/1", "Stored title", "Stored Co"),
    ],
)
async def test_ai_title_and_company_win_for_web_cards_only(
    factory, db, http, ai, sleep, key: str, expected_title: str, expected_company: str
) -> None:
    user_id = await make_user(db)
    async with db() as session:
        session.add(
            VacancySeenKey(user_id=user_id, external_key=key, first_seen_at=NOW)
        )
        session.add(
            Vacancy(
                user_id=user_id,
                external_key=key,
                url="https://jobs.example.com/acme/vacancy/1",
                job_link="https://jobs.example.com/acme/vacancy/1",
                title="Stored title",
                company="Stored Co",
                text="MATCH",
                posted_at=NOW,
                found_at=NOW,
                state="pending",
            )
        )
        await session.commit()

    await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    [card] = await vacancies(db)
    assert card.state == "new"
    assert (card.title, card.company) == (expected_title, expected_company)


@pytest.mark.parametrize(
    ("key", "expected_title"),
    [("web:src/abc", "Frontend Developer"), ("tg:early/1", "Stored title")],
)
async def test_ai_title_wins_for_web_when_an_earlier_post_is_promoted(
    factory, db, http, ai, sleep, key: str, expected_title: str
) -> None:
    user_id = await make_user(db)
    link = "https://jobs.example.com/acme/vacancy/1"
    async with db() as session:
        for external_key in (key, "tg:later/1"):
            session.add(
                VacancySeenKey(
                    user_id=user_id, external_key=external_key, first_seen_at=NOW
                )
            )
        # The pending post was found before the card it merges into.
        session.add(
            Vacancy(
                user_id=user_id,
                external_key=key,
                url=link,
                job_link=link,
                title="Stored title",
                text="MATCH",
                posted_at=NOW - timedelta(hours=3),
                found_at=NOW - timedelta(hours=3),
                state="pending",
            )
        )
        session.add(
            Vacancy(
                user_id=user_id,
                external_key="tg:later/1",
                url="https://t.me/later/1",
                job_link=link,
                title="Later title",
                text="MATCH later",
                posted_at=NOW - timedelta(hours=1),
                found_at=NOW - timedelta(hours=1),
                state="new",
                fit="medium",
            )
        )
        await session.commit()

    await evaluate_pending(factory, ai, at(NOW), config=CONFIG, sleep=sleep)

    [card] = await vacancies(db)
    assert card.external_key == key and card.state == "new"
    assert card.title == expected_title
