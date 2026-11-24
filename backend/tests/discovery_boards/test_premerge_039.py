"""PR #39 pre-merge findings at fetcher level (M1, M2, LOWs)."""

import json
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
import respx

from app.discovery import normalize, web_scan
from app.discovery.board_scan import fetch_board
from app.discovery.fetchers import (
    ashby,
    board_http,
    greenhouse,
    safe_http,
    site_listing,
    web_listing,
)
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
    assert page.skipped_count == 2
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


# --- R1: invisible and unencodable characters -------------------------------------

# Lone surrogate, C0, DEL, C1, zero-width, BOM, word joiner and invisible
# operators, a tag character, bidi controls.
HOSTILE = (
    "\udfff\ud800\x00\x07\x7f\x85\x9b\u200b\u200c\u200d\ufeff"
    "\u2060\u2061\u2064\U000e0041\u202e\u2066\u061c"
)


def test_strip_invisible_removes_unencodable_and_format_characters() -> None:
    cleaned = normalize.strip_invisible(f"Re{HOSTILE}act")

    assert cleaned == "React"
    cleaned.encode("utf-8")  # never raises


def test_strip_invisible_keeps_whitespace_and_letters() -> None:
    text = "Senior\tReact dev\nВакансия 🚀 €"

    assert normalize.strip_invisible(text) == text


def test_strip_invisible_for_text_keeps_format_characters_of_emoji() -> None:
    # Body text keeps Cf (ZWJ in emoji sequences) but loses Cs and Cc.
    family = "\U0001f468\u200d\U0001f469"
    text = f"a{family}\ud800\x00b"

    assert normalize.strip_invisible(text, keep_format=True) == f"a{family}b"


def test_geekjob_title_from_hostile_json_is_encodable() -> None:
    listing = site_listing.find_site_listing(SEARCH)
    assert listing is not None
    data = json.loads(
        b'{"nextpage": 0, "data": [{"id": "a1", "position": "x\\ud800y\\u200b z"}]}'
    )

    [job] = listing.parse_page(data, 1, None).jobs

    assert job.title == "xy z"
    job.title.encode("utf-8")


def test_board_titles_and_texts_are_cleaned_the_same_way() -> None:
    job = _ashby_job("j1", "2026-11-20T10:00:00Z")
    job["title"] = f"Dev{HOSTILE} Lead"
    job["descriptionPlain"] = "Line\ud800 one\x00\nLine two"

    post = ashby.to_raw_post("acme", job)

    assert post.title == "Dev Lead"
    assert post.text == "Line one\nLine two"
    assert board_http.cap_name("\ud800\u200b") is None


def test_web_job_json_ld_title_is_cleaned() -> None:
    from app.discovery.fetchers import web_job

    html = (
        '<html><head><script type="application/ld+json">'
        '{"@type": "JobPosting", "title": "Dev\\ud800 Ops", '
        '"description": "<p>Te\\ud800xt</p>"}'
        "</script></head><body></body></html>"
    )

    page = web_job.parse_job_page(html, "https://example.com/vacancy/1")

    assert page.title == "Dev Ops"
    assert "\ud800" not in page.text
    page.text.encode("utf-8")


# --- LOW: a pattern that filters every usable job ends the listing ------------------


async def test_pattern_filtering_every_job_stops_paging(
    respx_mock: respx.MockRouter,
) -> None:
    route = _api(
        respx_mock,
        {
            1: _gj_answer([_gj("a1"), _gj("a2")], 1, 2),
            2: _gj_answer([_gj("b1")], 2, 0),
        },
    )

    result = await web_scan.read_listing(
        SEARCH, "no-such-text", total_timeout_s=30, resolver=_resolve, pause_s=0
    )

    assert result.jobs == []
    assert route.call_count == 1


def test_pattern_filtered_page_reports_nothing_skipped() -> None:
    listing = site_listing.find_site_listing(SEARCH)
    assert listing is not None
    data = _gj_answer([_gj("a1"), _gj("x1", archived=True)], 1, 2)

    page = listing.parse_page(data, 1, "no-such-text")

    assert page.jobs == [] and page.skipped_count == 0


# --- N1: HTML listing titles ------------------------------------------------------

UTF7_PAGE = b'<meta charset="utf-7"><a href="/jobs/1">Dev +2AA- eng</a>'
PAGE_URL = "https://example.com/careers"


@pytest.mark.parametrize(
    "charset", ["utf-7", "UTF7", "unicode_escape", "raw-unicode-escape"]
)
def test_decode_refuses_codecs_that_make_surrogates_or_controls(charset: str) -> None:
    body = f'<meta charset="{charset}"><p>Dev +2AA- \\ud800 \\x00 eng</p>'.encode()

    text = safe_http._decode(body, None)

    assert "\ud800" not in text and "\x00" not in text
    text.encode("utf-8")
    assert safe_http._decode(body, charset) == text  # header charset too


def test_decode_keeps_real_charsets() -> None:
    body = "<p>Вакансия</p>".encode("cp1251")

    assert "Вакансия" in safe_http._decode(body, "windows-1251")


def test_html_listing_titles_are_cleaned() -> None:
    html = (
        '<a href="/jobs/1">Dev \ud800 eng\x00</a>'
        '<a href="/jobs/2"><h3>Ops\u200b\u202e Lead</h3></a>'
        '<a href="/jobs/3" title="QA\x07 lead"></a>'
    )

    titles = [job.title for job in web_listing.parse_listing(html, PAGE_URL, None).jobs]

    assert titles == ["Dev eng", "Ops Lead", "QA lead"]
    for title in titles:
        title.encode("utf-8")


def test_html_listing_title_of_only_invisible_characters_is_dropped() -> None:
    html = '<a href="/jobs/1">\u200b\ud800\x00</a><a href="/jobs/2">Dev</a>'

    jobs = web_listing.parse_listing(html, PAGE_URL, None).jobs

    assert [job.title for job in jobs] == ["Dev"]


def test_url_segment_fallback_title_is_cleaned() -> None:
    html = '<a href="/jobs/dev%00ops"></a>'

    [job] = web_listing.parse_listing(html, PAGE_URL, "/jobs/").jobs

    assert "\x00" not in job.title
    job.title.encode("utf-8")


def test_utf7_page_end_to_end_has_encodable_titles() -> None:
    text = safe_http._decode(UTF7_PAGE, None)

    [job] = web_listing.parse_listing(text, PAGE_URL, None).jobs

    job.title.encode("utf-8")
    assert "\ud800" not in job.title


# --- Greenhouse board name ------------------------------------------------------------


@respx.mock
async def test_greenhouse_board_name_is_cleaned() -> None:
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme").respond(
        200, content=b'{"name": "Acme \\ud800 \\u0000\\u200b"}'
    )

    async with httpx.AsyncClient() as client:
        name = await greenhouse.fetch_board_name(client, "acme")

    assert name == "Acme"


@respx.mock
async def test_greenhouse_board_name_of_only_invisible_characters_is_unreachable() -> (
    None
):
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme").respond(
        200, content=b'{"name": "\\ud800\\u0000"}'
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(BoardReadError):
            await greenhouse.fetch_board_name(client, "acme")
