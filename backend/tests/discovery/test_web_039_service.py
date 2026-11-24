"""PR #39 pre-merge findings in the hourly worker: geekjob paging past archived
pages (M2) and a Cloudflare challenge in the detail step (LOW)."""

from datetime import timedelta
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.discovery.web_scan import web_seen_key
from app.models.vacancy import Vacancy
from app.models.vacancy_source import VacancySource
from tests.discovery.test_service import NOW, get_source, make_user
from tests.discovery.test_web_service import (
    WATCHING_SINCE,
    check,
    make_web_source,
    queue_rows,
)
from tests.discovery.web_stubs import PUBLIC_IP, JobPage, Sites, WebSite

GEEKJOB = "https://geekjob.ru/vacancies?qs=react"
JSON_HEADERS = {"content-type": "application/json"}
ARCHIVED = {"modify": "1", "archived": {"$date": 1}}


async def _geekjob_source(
    db: async_sessionmaker[AsyncSession], user_id: str, url: str = GEEKJOB
) -> str:
    async with db() as session:
        source = VacancySource(
            user_id=user_id,
            kind="web",
            handle="placeholder",
            url=url,
            url_hash="g" * 64,
            default_name="geekjob.ru",
            display_name="geekjob.ru",
            initial_scan_completed_at=WATCHING_SINCE,
            last_checked_at=WATCHING_SINCE,
        )
        session.add(source)
        await session.flush()
        source.handle = source.id
        await session.commit()
        return source.id


async def test_hourly_scan_pages_past_an_all_archived_page(
    factory, db, http, ai, sleep, respx_mock: respx.MockRouter
) -> None:
    pages: dict[int, Any] = {
        1: {
            "nextpage": 2,
            "data": [{"id": "old1", "position": "Old", "log": ARCHIVED}],
        },
        2: {"nextpage": 0, "data": [{"id": "new1", "position": "React Dev"}]},
    }

    def api(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        return httpx.Response(200, headers=JSON_HEADERS, json=pages[page])

    route = respx_mock.get(f"https://{PUBLIC_IP}/json/find/vacancy").mock(
        side_effect=api
    )
    user_id = await make_user(db, description=None)
    source_id = await _geekjob_source(db, user_id)

    report = await check(factory, http, ai, sleep)

    assert report.sources_failed == 0
    assert route.call_count == 2
    async with db() as session:
        keys = set((await session.execute(select(Vacancy.external_key))).scalars())
    assert keys == {web_seen_key(source_id, "https://geekjob.ru/vacancy/new1")}
    assert (await get_source(db, source_id)).last_error is None


@pytest.fixture
def sites(respx_mock: respx.MockRouter) -> Sites:
    return Sites(respx_mock)


async def _rows(db: async_sessionmaker[AsyncSession]) -> dict[str, Vacancy]:
    async with db() as session:
        rows = (await session.execute(select(Vacancy))).scalars().all()
    return {row.url.rsplit("/", 1)[1]: row for row in rows}


async def test_blocked_job_page_counts_a_failure_for_every_due_row(
    factory, db, http, ai, sleep, sites: Sites
) -> None:
    site = sites.add(WebSite())
    user_id = await make_user(db)
    source_id = await make_web_source(db, user_id, site)
    await queue_rows(db, user_id, source_id, site, ["j1", "j2", "j3"])
    for job_id in ("j1", "j2", "j3"):
        site.pages[job_id] = JobPage(text=f"Job {job_id}")
        site.blocked_jobs.add(job_id)

    await check(factory, http, ai, sleep)

    # One challenged page is enough: no more requests, every due row counts.
    assert site.job_requests == ["j1"]
    rows = await _rows(db)
    assert {key: row.detail_attempts for key, row in rows.items()} == {
        "j1": 1,
        "j2": 1,
        "j3": 1,
    }


async def test_blocked_site_releases_its_backlog_after_three_checks(
    factory, db, http, ai, sleep, sites: Sites
) -> None:
    site = sites.add(WebSite())
    user_id = await make_user(db)
    source_id = await make_web_source(db, user_id, site)
    await queue_rows(db, user_id, source_id, site, ["j1", "j2", "j3"])
    site.blocked_jobs.update({"j1", "j2", "j3"})

    for hours in (0, 1):
        await check(factory, http, ai, sleep, NOW + timedelta(hours=hours))
    rows = await _rows(db)
    assert {key: row.detail_attempts for key, row in rows.items()} == {
        "j1": 2,
        "j2": 2,
        "j3": 2,
    }

    await check(factory, http, ai, sleep, NOW + timedelta(hours=2))

    # One request per check; after the third every row was released to
    # title-only rating (and then rated): none waits for its job page.
    assert site.job_requests == ["j1", "j1", "j1"]
    assert all(not row.needs_detail for row in (await _rows(db)).values())


# --- hostile geekjob titles (R1) -------------------------------------------------------


async def test_hourly_scan_stores_jobs_whose_titles_had_lone_surrogates(
    factory, db, http, ai, sleep, respx_mock: respx.MockRouter
) -> None:
    body = (
        b'{"nextpage": 0, "data": ['
        b'{"id": "bad1", "position": "React\\ud800 Dev\\u0000"},'
        b'{"id": "ok1", "position": "Vue Dev"}]}'
    )
    respx_mock.get(f"https://{PUBLIC_IP}/json/find/vacancy").respond(
        200, headers=JSON_HEADERS, content=body
    )
    user_id = await make_user(db, description=None)
    source_id = await _geekjob_source(db, user_id)

    report = await check(factory, http, ai, sleep)

    assert report.sources_failed == 0
    rows = await _rows(db)
    assert {key: row.title for key, row in rows.items()} == {
        "bad1": "React Dev",
        "ok1": "Vue Dev",
    }
    assert (await get_source(db, source_id)).last_error is None


# --- boards behind a challenge ----------------------------------------------------------


async def test_board_behind_a_challenge_gets_the_blocked_reason(
    factory, db, http, ai, sleep, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get("https://api.ashbyhq.com/posting-api/job-board/acme").respond(
        403, headers={"cf-mitigated": "challenge"}
    )
    user_id = await make_user(db, description=None)
    async with db() as session:
        source = VacancySource(
            user_id=user_id,
            kind="ashby",
            handle="acme",
            default_name="Acme",
            display_name="Acme",
            initial_scan_completed_at=WATCHING_SINCE,
            last_checked_at=WATCHING_SINCE,
        )
        session.add(source)
        await session.commit()
        source_id = source.id

    report = await check(factory, http, ai, sleep)

    assert report.sources_failed == 1
    source = await get_source(db, source_id)
    assert source.last_error == "This site blocks automated readers"
    assert source.failing_since == NOW


# --- N1: HTML listing in a hostile charset ------------------------------------------


async def test_hourly_scan_stores_rows_from_a_utf7_html_listing(
    factory, db, http, ai, sleep, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"https://{PUBLIC_IP}/careers").respond(
        200,
        headers={"content-type": "text/html"},
        content=(
            b'<meta charset="utf-7">'
            b'<a href="/jobs/1">Dev +2AA- eng</a><a href="/jobs/2">QA lead</a>'
        ),
    )
    user_id = await make_user(db, description=None)
    source_id = await _geekjob_source(db, user_id, "https://jobs.example.com/careers")

    report = await check(factory, http, ai, sleep)

    assert report.sources_failed == 0
    rows = await _rows(db)
    assert set(rows) == {"1", "2"}
    for row in rows.values():
        assert row.title is not None
        row.title.encode("utf-8")
    assert (await get_source(db, source_id)).last_error is None
