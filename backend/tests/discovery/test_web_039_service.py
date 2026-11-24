"""PR #39 pre-merge findings in the hourly worker: geekjob paging past archived
pages (M2) and a Cloudflare challenge in the detail step (LOW)."""

from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.discovery.web_scan import web_seen_key
from app.models.vacancy import Vacancy
from app.models.vacancy_source import VacancySource
from tests.discovery.test_service import get_source, make_user
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


async def _geekjob_source(db: async_sessionmaker[AsyncSession], user_id: str) -> str:
    async with db() as session:
        source = VacancySource(
            user_id=user_id,
            kind="web",
            handle="placeholder",
            url=GEEKJOB,
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


async def test_blocked_job_page_stops_the_detail_step_for_the_source(
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

    # One challenged page is enough: the other rows wait for the next check.
    assert site.job_requests == ["j1"]
    async with db() as session:
        rows = (await session.execute(select(Vacancy))).scalars().all()
    attempts = {row.url.rsplit("/", 1)[1]: row.detail_attempts for row in rows}
    assert attempts == {"j1": 1, "j2": 0, "j3": 0}
