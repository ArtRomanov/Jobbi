"""Site listing adapters (spec 010 §2.6): geekjob.ru search links read via JSON."""

import json
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest
import respx

from app.discovery import web_scan
from app.discovery.fetchers import site_listing
from app.discovery.fetchers.safe_http import PageFetchError
from app.discovery.fetchers.web_listing import MAX_TITLE_CHARS, ListingJob
from tests.discovery_boards.conftest import FIXTURES

PUBLIC_IP = "93.184.216.34"
JSON_HEADERS = {"content-type": "application/json"}
REAL = json.loads((FIXTURES / "geekjob_react.json").read_text(encoding="utf-8"))
SEARCH = "https://geekjob.ru/vacancies?qs=react"


async def _resolve(host: str, port: int) -> list[str]:
    return [PUBLIC_IP]


def _query(url: str) -> list[tuple[str, str]]:
    return parse_qsl(urlsplit(url).query)


def _item(item_id: str, position: str = "Dev", **extra: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": item_id,
        "position": position,
        "company": {"name": "Acme"},
        "log": {"modify": "21 ноября", "archived": None},
    }
    item.update(extra)
    return item


def _answer(items: list[Any], *, page: int = 1, nextpage: Any = 0) -> dict[str, Any]:
    return {"page": page, "nextpage": nextpage, "pagecount": 1, "data": items}


# --- detection --------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        SEARCH,
        "http://geekjob.ru/vacancies?qs=react",
        "https://www.geekjob.ru/vacancies?qs=react",
        "https://GEEKJOB.RU/vacancies?qs=react",
        "https://GEEKJOB.RU./vacancies?qs=x",  # trailing-dot host
        "https://www.geekjob.ru./vacancies?rm=1",
        "https://geekjob.ru/vacancies/?qs=react",
        "https://geekjob.ru/vacancies/2?qs=react",
        "https://geekjob.ru/vacancies?rm=1",
        "https://geekjob.ru/vacancies?t=52,107",
        "https://geekjob.ru/vacancies?na=1&utm_source=tg",
    ],
)
def test_geekjob_search_links_get_the_adapter(url: str) -> None:
    listing = site_listing.find_site_listing(url)

    assert listing is not None
    assert listing.name == "geekjob"


@pytest.mark.parametrize(
    "url",
    [
        "https://geekjob.ru/vacancies",  # no filter: the server-rendered page
        "https://geekjob.ru/vacancies?utm_source=tg",
        "https://geekjob.ru/vacancies?qs=",
        "https://geekjob.ru/vacancies?qs=%20%20",
        "https://geekjob.ru/vacancies?t=abc",
        "https://geekjob.ru/vacancies?sort=1",
        "https://geekjob.ru/vacancies?page=2",
        # The site's own script never reads these from the page URL.
        "https://geekjob.ru/vacancies?or=52,107",
        "https://geekjob.ru/vacancies?money=200000",
        "https://geekjob.ru/vacancies?f=1,2",
        "https://geekjob.ru../vacancies?qs=x",
        "https://geekjob.ru/vacancy/6b01b96bc859285a74045e0c?qs=react",
        "https://geekjob.ru/vacancies/x?qs=react",
        "https://geekjob.ru/json/find/vacancy?qs=react",
        "https://geekjob.ru:8443/vacancies?qs=react",
        "https://user@geekjob.ru/vacancies?qs=react",
        "https://my.geekjob.ru/vacancies?qs=react",
        "https://geekjob.ru.evil.com/vacancies?qs=react",
        "https://evil.com/geekjob.ru/vacancies?qs=react",
        "https://example.com/vacancies?qs=react",
        "ftp://geekjob.ru/vacancies?qs=react",
        "not a url",
        "",
    ],
)
def test_other_links_keep_the_html_path(url: str) -> None:
    assert site_listing.find_site_listing(url) is None


# --- parameters -------------------------------------------------------------------


def test_filters_are_copied_and_newest_first_is_forced() -> None:
    listing = site_listing.find_site_listing(
        "https://geekjob.ru/vacancies/3?qs=react%20native&rm=1&rl=1&pt=1&ih=1&na=1"
        "&t=52,107&or=1,2&s=1&money=200000&sort=2&page=7&utm_source=tg&foo=bar"
    )
    assert listing is not None

    url = listing.page_url(1)

    assert url.startswith("https://geekjob.ru/json/find/vacancy?")
    # Only what the site's script reads from the page URL; `money` is always
    # the script's own default and `or` is never read.
    assert _query(url) == [
        ("page", "1"),
        ("qs", "react native"),
        ("t", "52,107"),
        ("s", "1"),
        ("money", "120000"),
        ("pt", "1"),
        ("ih", "1"),
        ("rm", "1"),
        ("rl", "1"),
        ("na", "1"),
        ("sort", "1"),
    ]
    assert dict(_query(listing.page_url(4)))["page"] == "4"


def test_only_salary_flag_gets_the_sites_default_amount() -> None:
    listing = site_listing.find_site_listing("https://geekjob.ru/vacancies?s=1")
    assert listing is not None

    assert dict(_query(listing.page_url(1)))["money"] == "120000"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("t=1,2,3", "1,2,3"),
        ("t=1,,2", None),
        ("t=1;2", None),
        ("t=" + ",".join(["1"] * 51), None),
        ("t=1234567", None),
    ],
)
def test_tag_filter_must_be_a_short_list_of_numbers(
    raw: str, expected: str | None
) -> None:
    listing = site_listing.find_site_listing(f"https://geekjob.ru/vacancies?qs=x&{raw}")
    assert listing is not None

    assert dict(_query(listing.page_url(1))).get("t") == expected


def test_search_text_is_trimmed_and_capped() -> None:
    long_text = "a" * (site_listing.MAX_QUERY_CHARS + 50)
    listing = site_listing.find_site_listing(
        f"https://geekjob.ru/vacancies?qs=%20{long_text}%20"
    )
    assert listing is not None

    assert dict(_query(listing.page_url(1)))["qs"] == "a" * site_listing.MAX_QUERY_CHARS


def test_cyrillic_search_text_is_kept() -> None:
    listing = site_listing.find_site_listing(
        "https://geekjob.ru/vacancies?qs=%D1%84%D1%80%D0%BE%D0%BD%D1%82"
    )
    assert listing is not None

    assert dict(_query(listing.page_url(1)))["qs"] == "фронт"


# --- JSON mapping -----------------------------------------------------------------


def test_real_answer_maps_to_job_links_and_titles() -> None:
    listing = site_listing.find_site_listing(SEARCH)
    assert listing is not None

    page = listing.parse_page(REAL, 1, None)

    # Duplicates and archived jobs are dropped; site order is kept.
    assert page.jobs == [
        ListingJob(
            url="https://geekjob.ru/vacancy/6b01b96bc859285a74045e0c",
            title="Product Engineer",
        ),
        ListingJob(
            url="https://geekjob.ru/vacancy/6afc5735f96daab76a0a717e",
            title="Senior Fullstack Developer (Laravel + React) / Technical Lead",
        ),
        *page.jobs[2:],
    ]
    assert len(page.jobs) == 6
    assert "https://geekjob.ru/vacancy/623b065bf2f5ad66cb3f39f5" not in {
        job.url for job in page.jobs
    }
    assert page.next_url is None  # nextpage == 0
    assert page.ats_hint is None


def test_next_page_follows_nextpage() -> None:
    listing = site_listing.find_site_listing(SEARCH)
    assert listing is not None

    page = listing.parse_page(_answer([_item("a1")], page=1, nextpage=2), 1, None)

    assert page.next_url == listing.page_url(2)


@pytest.mark.parametrize("nextpage", [0, None, "2", True, -1, 1, 2.5, [2]])
def test_unusable_nextpage_ends_the_listing(nextpage: Any) -> None:
    listing = site_listing.find_site_listing(SEARCH)
    assert listing is not None

    page = listing.parse_page(_answer([_item("a1")], nextpage=nextpage), 1, None)

    assert page.next_url is None


def test_job_link_contains_filters_job_urls() -> None:
    listing = site_listing.find_site_listing(SEARCH)
    assert listing is not None
    data = _answer([_item("aa11"), _item("bb22")])

    assert [j.url for j in listing.parse_page(data, 1, "BB2").jobs] == [
        "https://geekjob.ru/vacancy/bb22"
    ]


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        "data",
        42,
        {},
        {"data": None},
        {"data": "x"},
        {"data": {"0": _item("a1")}},
    ],
)
def test_wrong_shapes_give_an_empty_page(data: Any) -> None:
    listing = site_listing.find_site_listing(SEARCH)
    assert listing is not None

    page = listing.parse_page(data, 1, None)

    assert page.jobs == [] and page.next_url is None


def test_hostile_items_are_skipped() -> None:
    listing = site_listing.find_site_listing(SEARCH)
    assert listing is not None
    items: list[Any] = [
        "not a dict",
        None,
        {"position": "no id"},
        _item(""),
        _item(123),
        _item("../../admin"),
        _item("a/b"),
        _item("a?x=1"),
        _item("x" * 65),
        _item({"$oid": "a1"}),
        _item("ok1", position=None),
        _item("ok2", position=""),
        _item("ok3", position="   "),
        _item("ok4", position=["x"]),
        _item("ok5", log="archived"),
        _item("ok6", log={"archived": {"$date": 1}}),
        _item("good", position="  Senior\n\tReact   Dev  "),
        _item("long", position="z" * 1000),
    ]

    page = listing.parse_page(_answer(items), 1, None)

    assert page.jobs == [
        ListingJob(url="https://geekjob.ru/vacancy/good", title="Senior React Dev"),
        ListingJob(url="https://geekjob.ru/vacancy/long", title="z" * MAX_TITLE_CHARS),
    ]


def test_huge_answers_are_capped() -> None:
    listing = site_listing.find_site_listing(SEARCH)
    assert listing is not None
    items = [_item(f"id{i}") for i in range(site_listing.MAX_ITEMS_PER_PAGE + 50)]

    page = listing.parse_page(_answer(items), 1, None)

    assert len(page.jobs) == site_listing.MAX_ITEMS_PER_PAGE


def test_parse_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    listing = site_listing.find_site_listing(SEARCH)
    assert listing is not None

    def boom(*args: Any) -> Any:
        raise RuntimeError("parser bug")

    monkeypatch.setattr(site_listing, "_geekjob_jobs", boom)

    page = listing.parse_page(_answer([_item("a1")]), 1, None)

    assert page.jobs == [] and page.next_url is None


# --- read_listing with the adapter ------------------------------------------------


def _api(respx_mock: respx.MockRouter, pages: dict[int, Any]) -> respx.Route:
    def handler(request: httpx.Request) -> httpx.Response:
        number = int(request.url.params["page"])
        answer = pages.get(number)
        if isinstance(answer, httpx.Response):
            return answer
        if answer is None:
            return httpx.Response(
                200, headers=JSON_HEADERS, json=_answer([], page=number)
            )
        return httpx.Response(200, headers=JSON_HEADERS, json=answer)

    return respx_mock.get(f"https://{PUBLIC_IP}/json/find/vacancy").mock(
        side_effect=handler
    )


async def _read(url: str = SEARCH, **kwargs: Any) -> web_scan.ListingRead:
    return await web_scan.read_listing(
        url,
        kwargs.pop("job_link_contains", None),
        total_timeout_s=30,
        resolver=_resolve,
        pause_s=0,
        **kwargs,
    )


async def test_read_listing_uses_the_json_endpoint_through_safe_http(
    respx_mock: respx.MockRouter,
) -> None:
    route = _api(respx_mock, {1: REAL})

    result = await _read()

    assert result.pages_read == 1
    assert [job.title for job in result.jobs][:2] == [
        "Product Engineer",
        "Senior Fullstack Developer (Laravel + React) / Technical Lead",
    ]
    assert result.ats_hint is None
    request = route.calls.last.request
    # Pinned to the checked IP, with the real host name and the JSON accept.
    assert request.headers["host"] == "geekjob.ru"
    assert request.headers["accept"] == "application/json"
    assert dict(_query(str(request.url))) == {"page": "1", "qs": "react", "sort": "1"}


async def test_read_listing_pages_until_nextpage_is_zero(
    respx_mock: respx.MockRouter,
) -> None:
    route = _api(
        respx_mock,
        {
            1: _answer([_item("a1"), _item("a2")], page=1, nextpage=2),
            2: _answer([_item("b1")], page=2, nextpage=0),
            3: _answer([_item("c1")], page=3, nextpage=0),
        },
    )

    result = await _read()

    assert [job.url.rsplit("/", 1)[1] for job in result.jobs] == ["a1", "a2", "b1"]
    assert result.pages_read == 2
    assert route.call_count == 2


async def test_read_listing_stops_at_five_pages(respx_mock: respx.MockRouter) -> None:
    pages = {n: _answer([_item(f"p{n}")], page=n, nextpage=n + 1) for n in range(1, 9)}
    route = _api(respx_mock, pages)

    result = await _read()

    assert result.pages_read == web_scan.MAX_LISTING_PAGES == 5
    assert route.call_count == 5


async def test_read_listing_stops_after_a_page_with_a_seen_job(
    respx_mock: respx.MockRouter,
) -> None:
    route = _api(
        respx_mock,
        {
            1: _answer([_item("a1")], page=1, nextpage=2),
            2: _answer([_item("b1")], page=2, nextpage=3),
            3: _answer([_item("c1")], page=3, nextpage=0),
        },
    )

    result = await _read(stop_after=lambda jobs: any("b1" in j.url for j in jobs))

    assert result.pages_read == 2
    assert route.call_count == 2


async def test_read_listing_keeps_pages_before_a_failing_one(
    respx_mock: respx.MockRouter,
) -> None:
    _api(
        respx_mock,
        {
            1: _answer([_item("a1")], page=1, nextpage=2),
            2: httpx.Response(500),
        },
    )

    result = await _read()

    assert [job.url.rsplit("/", 1)[1] for job in result.jobs] == ["a1"]


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(500), "unreachable"),
        (
            httpx.Response(200, headers={"content-type": "text/html"}, text="<html/>"),
            "not_json",
        ),
        (httpx.Response(200, headers=JSON_HEADERS, content=b"{broken"), "not_json"),
        (httpx.Response(403, headers={"cf-mitigated": "challenge"}), "blocked"),
    ],
)
async def test_read_listing_first_page_failure_raises(
    respx_mock: respx.MockRouter, response: httpx.Response, reason: str
) -> None:
    _api(respx_mock, {1: response})

    with pytest.raises(PageFetchError) as exc_info:
        await _read()

    assert exc_info.value.reason == reason


async def test_read_listing_hostile_json_gives_no_jobs(
    respx_mock: respx.MockRouter,
) -> None:
    _api(
        respx_mock, {1: {"data": [{"id": "../x", "position": "x"}] * 10, "nextpage": 2}}
    )

    result = await _read()

    assert result.jobs == [] and result.pages_read == 1


async def test_other_sites_still_use_the_html_path(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.get(f"https://{PUBLIC_IP}/vacancies").respond(
        200,
        headers={"content-type": "text/html"},
        text='<a href="/vacancy/1"><h2>Backend Developer</h2></a>',
    )

    result = await _read("https://geekjob.ru/vacancies")

    assert [job.title for job in result.jobs] == ["Backend Developer"]
    assert route.call_count == 1
