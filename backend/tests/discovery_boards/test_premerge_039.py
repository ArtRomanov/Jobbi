"""PR #39 pre-merge findings at fetcher level (M1, M2, LOWs)."""

from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
import respx

from app.discovery import web_scan
from app.discovery.board_scan import fetch_board
from app.discovery.fetchers import ashby, board_http, site_listing
from app.discovery.fetchers.errors import BoardReadError
from app.discovery.fetchers.safe_http import PageFetchError
from app.services.vacancy_source_parsing import ParsedSource, parse_source_input

PUBLIC_IP = "93.184.216.34"
JSON_HEADERS = {"content-type": "application/json"}
SEARCH = "https://geekjob.ru/vacancies?qs=react"
ASHBY_API = "https://api.ashbyhq.com/posting-api/job-board/acme"


async def _resolve(host: str, port: int) -> list[str]:
    return [PUBLIC_IP]


def _ashby_job(job_id: str, published: Any) -> dict[str, Any]:
    return {
        "id": job_id,
        "title": f"Job {job_id}",
        "jobUrl": f"https://jobs.ashbyhq.com/acme/{job_id}",
        "publishedAt": published,
        "descriptionPlain": "Text",
    }


def _gj(item_id: str, *, archived: bool = False) -> dict[str, Any]:
    return {
        "id": item_id,
        "position": f"Dev {item_id}",
        "log": {"modify": "1 ноября", "archived": {"$date": 1} if archived else None},
    }


def _gj_answer(items: list[Any], page: int, nextpage: int) -> dict[str, Any]:
    return {"page": page, "nextpage": nextpage, "data": items}


# --- M1: hostile Ashby dates ----------------------------------------------------------


@pytest.mark.parametrize(
    "value", ["0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"]
)
def test_out_of_range_offset_dates_read_as_undated(value: str) -> None:
    assert ashby.job_posted_at(_ashby_job("a", value)) is None


@respx.mock
async def test_one_hostile_date_does_not_lose_the_rest_of_the_board() -> None:
    respx.get(ASHBY_API).respond(
        200,
        json={
            "jobs": [
                _ashby_job("bad-low", "0001-01-01T00:00:00+01:00"),
                _ashby_job("good", "2026-11-20T10:00:00+00:00"),
                _ashby_job("bad-high", "9999-12-31T23:59:59-01:00"),
            ]
        },
    )
    now = datetime(2026, 11, 21, 12, 0)

    async with httpx.AsyncClient() as client:
        result = await fetch_board(
            client,
            "ashby",
            "acme",
            set(),
            now=now,
            cutoff=now - timedelta(days=7),
            initial=False,
        )

    assert {post.external_key for post in result.posts} == {
        "ashby:acme/bad-low",
        "ashby:acme/good",
        "ashby:acme/bad-high",
    }


# --- M2: pages with only archived items -----------------------------------------------


def test_adapter_reports_items_separately_from_usable_jobs() -> None:
    listing = site_listing.find_site_listing(SEARCH)
    assert listing is not None

    page = listing.parse_page(
        _gj_answer([_gj("a1", archived=True), _gj("a2", archived=True)], 1, 2), 1, None
    )

    assert page.jobs == []
    assert page.item_count == 2
    assert page.next_url == listing.page_url(2)


def _api(respx_mock: respx.MockRouter, pages: dict[int, Any]) -> respx.Route:
    def handler(request: httpx.Request) -> httpx.Response:
        number = int(request.url.params["page"])
        body = pages.get(number, _gj_answer([], number, 0))
        return httpx.Response(200, headers=JSON_HEADERS, json=body)

    return respx_mock.get(f"https://{PUBLIC_IP}/json/find/vacancy").mock(
        side_effect=handler
    )


async def _read(**kwargs: Any) -> web_scan.ListingRead:
    return await web_scan.read_listing(
        SEARCH, None, total_timeout_s=30, resolver=_resolve, pause_s=0, **kwargs
    )


async def test_all_archived_page_does_not_stop_paging(
    respx_mock: respx.MockRouter,
) -> None:
    route = _api(
        respx_mock,
        {
            1: _gj_answer([_gj("x1", archived=True), _gj("x2", archived=True)], 1, 2),
            2: _gj_answer([_gj("b1")], 2, 0),
        },
    )

    result = await _read()

    assert [job.url.rsplit("/", 1)[1] for job in result.jobs] == ["b1"]
    assert result.pages_read == 2
    assert route.call_count == 2


async def test_archived_pages_still_respect_the_page_cap(
    respx_mock: respx.MockRouter,
) -> None:
    pages = {
        n: _gj_answer([_gj(f"x{n}", archived=True)], n, n + 1) for n in range(1, 9)
    }
    route = _api(respx_mock, pages)

    result = await _read()

    assert result.jobs == []
    assert route.call_count == web_scan.MAX_LISTING_PAGES


async def test_seen_job_still_stops_after_an_archived_page(
    respx_mock: respx.MockRouter,
) -> None:
    route = _api(
        respx_mock,
        {
            1: _gj_answer([_gj("x1", archived=True)], 1, 2),
            2: _gj_answer([_gj("seen")], 2, 3),
            3: _gj_answer([_gj("c1")], 3, 0),
        },
    )

    await _read(stop_after=lambda jobs: True)

    assert route.call_count == 2


async def test_empty_page_still_stops(respx_mock: respx.MockRouter) -> None:
    route = _api(respx_mock, {1: _gj_answer([], 1, 2), 2: _gj_answer([_gj("b")], 2, 0)})

    result = await _read()

    assert result.jobs == [] and route.call_count == 1


# --- LOW: parser failure is "could not open", not "no vacancies" ----------------------


def test_parser_exception_is_an_unreadable_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing = site_listing.find_site_listing(SEARCH)
    assert listing is not None

    def boom(*args: Any) -> Any:
        raise RuntimeError("parser bug")

    monkeypatch.setattr(site_listing, "_geekjob_jobs", boom)

    with pytest.raises(PageFetchError) as exc_info:
        listing.parse_page(_gj_answer([_gj("a1")], 1, 0), 1, None)
    assert exc_info.value.reason == "unreachable"


# --- LOW: geekjob JSON requests follow no redirects -----------------------------------


async def test_geekjob_json_redirect_is_not_followed(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.get(f"https://{PUBLIC_IP}/json/find/vacancy").respond(
        302, headers={"location": "https://geekjob.ru/json/find/vacancy?page=1&qs=x"}
    )

    with pytest.raises(PageFetchError) as exc_info:
        await _read()

    assert exc_info.value.reason == "unreachable"
    assert route.call_count == 1


# --- LOW: control characters in geekjob titles ---------------------------------------


def test_titles_lose_nul_and_bidi_controls() -> None:
    listing = site_listing.find_site_listing(SEARCH)
    assert listing is not None
    item = {
        "id": "a1",
        "position": "Re\x00act\u202e Dev\u2066e\u2069\u200f\u061c\x7f lead",
        "log": {},
    }

    [job] = listing.parse_page(_gj_answer([item], 1, 0), 1, None).jobs

    assert job.title == "React Deve lead"


def test_title_of_only_controls_is_dropped() -> None:
    listing = site_listing.find_site_listing(SEARCH)
    assert listing is not None
    item = {"id": "a1", "position": "\x00\u202e\u2066", "log": {}}

    assert listing.parse_page(_gj_answer([item], 1, 0), 1, None).jobs == []


# --- LOW: Ashby job URL stripped, fragment accepted ----------------------------------


def test_ashby_job_url_is_stripped() -> None:
    job = _ashby_job("j1", "2026-11-20T10:00:00Z")
    job["jobUrl"] = "  https://jobs.ashbyhq.com/acme/j1 \n"

    [usable] = ashby.parse_board("acme", {"jobs": [job]})
    post = ashby.to_raw_post("acme", usable)

    assert post.url == "https://jobs.ashbyhq.com/acme/j1"


@pytest.mark.parametrize(
    "raw",
    [
        "jobs.ashbyhq.com/acme#x",
        "https://jobs.ashbyhq.com/acme/#openings",
        "https://jobs.ashbyhq.com/acme?utm_source=x#top",
    ],
)
def test_ashby_link_with_a_fragment_is_accepted(raw: str) -> None:
    assert parse_source_input(raw) == ParsedSource(kind="ashby", handle="acme")


# --- LOW: Cloudflare challenge on board APIs -------------------------------------------


@pytest.mark.parametrize("status", [403, 429, 503])
@respx.mock
async def test_board_api_challenge_is_blocked(status: int) -> None:
    respx.get(ASHBY_API).respond(
        status, headers={"cf-mitigated": "challenge", "server": "cloudflare"}
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(BoardReadError) as exc_info:
            await board_http.get_bytes(client, ASHBY_API)

    assert exc_info.value.reason == "blocked"


@respx.mock
async def test_board_api_plain_403_stays_unreachable() -> None:
    respx.get(ASHBY_API).respond(403, headers={"server": "cloudflare"})

    async with httpx.AsyncClient() as client:
        with pytest.raises(BoardReadError) as exc_info:
            await board_http.get_bytes(client, ASHBY_API)

    assert exc_info.value.reason == "unreachable"
