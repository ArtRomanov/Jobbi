"""Tests for reading one job page of a web source."""

import datetime as dt
import json
import socket
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
import trafilatura
import trafilatura.downloads

from app.discovery.fetchers import web_job
from app.discovery.fetchers.board_http import MAX_NAME_CHARS, MAX_TEXT_CHARS
from app.discovery.fetchers.safe_http import PageFetchError, UnsafeUrlError, make_client
from app.discovery.fetchers.web_job import JobPage, fetch_job, parse_job_page

JOBS = Path(__file__).parent / "fixtures" / "web" / "jobs"
PUBLIC_IP = "93.184.216.34"
HTML = {"content-type": "text/html; charset=utf-8"}
PAGE_URL = "https://jobs.example.com/vacancy/1"


def _fixture(name: str) -> str:
    return (JOBS / name).read_text(encoding="utf-8")


def _ld(*blocks: Any, body: str = "<main><p>Page body text</p></main>") -> str:
    scripts = "".join(
        f'<script type="application/ld+json">{b if isinstance(b, str) else json.dumps(b)}</script>'
        for b in blocks
    )
    return f"<html><head>{scripts}</head><body>{body}</body></html>"


def _posting(**fields: Any) -> dict[str, Any]:
    return {"@context": "https://schema.org", "@type": "JobPosting", **fields}


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any download attempt by trafilatura or a raw socket fails the test."""

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("network access during parsing")

    monkeypatch.setattr(trafilatura, "fetch_url", _boom)
    monkeypatch.setattr(trafilatura.downloads, "fetch_url", _boom)
    monkeypatch.setattr(trafilatura.downloads, "fetch_response", _boom)
    monkeypatch.setattr(socket.socket, "connect", _boom)


# --- real pages ---------------------------------------------------------------


def test_geekjob_json_ld_gives_text_date_title_company() -> None:
    page = parse_job_page(
        _fixture("geekjob.html"), "https://geekjob.ru/vacancy/6b0412760e9260dd7d039713"
    )

    assert page.posted_at == dt.datetime(2026, 11, 23)
    assert page.title == "Product Design Lead в Core Product"
    assert page.company == "Профи.ру"
    assert "Core Product отвечает за основной сценарий сервиса" in page.text
    assert "<" not in page.text
    assert "Работодателям" not in page.text  # site menu
    assert "Войти / Регистрация" not in page.text


@pytest.mark.parametrize(
    ("name", "url", "body_phrase", "menu_phrases"),
    [
        (
            "yandex.html",
            "https://yandex.ru/jobs/vacancies/produktoviy-analitik-49741",
            "Исследуйте, как люди пользуются сервисами Яндекса",
            ["Как мы нанимаем", "Офисы"],
        ),
        (
            "ingamejob.html",
            "https://ingamejob.com/en/job/legal-counsel-product-privacy",
            "Vizor Games is hiring a dedicated in-house Privacy & Product Counsel",
            ["Post CV", "Sign up", "View all vacancies from"],
        ),
        (
            "ostrovok.html",
            "https://career.ostrovok.ru/vacancy/3490",
            "Опыт работы с DBT",
            ["Стажировка", "Новослободская", "Human Capital"],
        ),
    ],
)
def test_pages_without_job_posting_use_main_text(
    name: str, url: str, body_phrase: str, menu_phrases: list[str]
) -> None:
    page = parse_job_page(_fixture(name), url)

    assert body_phrase in page.text
    for phrase in menu_phrases:
        assert phrase not in page.text
    assert "<" not in page.text
    assert (page.posted_at, page.title, page.company) == (None, None, None)


# --- JSON-LD shapes -----------------------------------------------------------


def test_description_html_becomes_text() -> None:
    page = parse_job_page(
        _ld(_posting(description="<p>Build <b>APIs</b></p><ul><li>Python</li></ul>")),
        PAGE_URL,
    )
    assert page.text == "Build APIs\nPython"


def test_escaped_description_html_is_unescaped_first() -> None:
    page = parse_job_page(
        _ld(_posting(description="&lt;p&gt;Build APIs&lt;/p&gt;&lt;p&gt;Remote&lt;/p&gt;")),
        PAGE_URL,
    )
    assert page.text == "Build APIs\nRemote"


def test_array_block_and_list_type() -> None:
    html = _ld(
        [
            {"@type": "Organization", "name": "Acme"},
            {"@type": ["Thing", "JobPosting"], "description": "From array", "title": "Dev"},
        ]
    )
    page = parse_job_page(html, PAGE_URL)
    assert (page.text, page.title) == ("From array", "Dev")


def test_graph_block() -> None:
    html = _ld(
        {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "WebPage", "name": "Jobs"},
                _posting(description="From graph", hiringOrganization="Acme Ltd"),
            ],
        }
    )
    page = parse_job_page(html, PAGE_URL)
    assert (page.text, page.company) == ("From graph", "Acme Ltd")


def test_bad_json_block_is_skipped_and_next_one_used() -> None:
    html = _ld("{not json", "[" * 100_000, _posting(description="Good block"))
    page = parse_job_page(html, PAGE_URL)
    assert page.text == "Good block"


def test_company_object_or_list_and_fields_are_cleaned_and_capped() -> None:
    long_title = "Senior  &amp;\n Lead " + "x" * 400
    html = _ld(
        _posting(
            description="d",
            title=long_title,
            hiringOrganization=[{"@type": "Organization", "name": " Acme\tInc "}],
        )
    )
    page = parse_job_page(html, PAGE_URL)
    assert page.company == "Acme Inc"
    assert page.title is not None
    assert page.title.startswith("Senior & Lead x")
    assert len(page.title) == MAX_NAME_CHARS


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-11-20", dt.datetime(2026, 11, 20)),
        ("2026-11-20T10:30:00Z", dt.datetime(2026, 11, 20, 10, 30)),
        ("2026-11-20T10:30:00+03:00", dt.datetime(2026, 11, 20, 7, 30)),
        ("2026-11-20T10:30:00", dt.datetime(2026, 11, 20, 10, 30)),
        ("  2026-11-20 ", dt.datetime(2026, 11, 20)),
        ("yesterday", None),
        ("2026-13-45", None),
        ("", None),
        (20261120, None),
        (None, None),
        ("9" * 10_000, None),
    ],
)
def test_date_posted(value: Any, expected: dt.datetime | None) -> None:
    page = parse_job_page(_ld(_posting(description="d", datePosted=value)), PAGE_URL)
    assert page.posted_at == expected


def test_empty_description_falls_back_to_page_text_but_keeps_fields() -> None:
    body = "<nav>Home Jobs About</nav><main><h1>Backend developer</h1>" + (
        "<p>We are looking for a backend developer to build our payments API "
        "with Python and PostgreSQL. You will own services end to end.</p>" * 3
    ) + "</main><footer>Copyright Acme</footer>"
    html = _ld(_posting(description="  ", title="Backend", datePosted="2026-01-02"), body=body)

    page = parse_job_page(html, PAGE_URL)

    assert "build our payments API" in page.text
    assert "Copyright Acme" not in page.text
    assert page.title == "Backend"
    assert page.posted_at == dt.datetime(2026, 1, 2)


def test_trafilatura_nothing_falls_back_to_main(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_job.trafilatura, "extract", lambda *a, **k: None)
    html = (
        "<html><body><nav>Menu</nav><main><p>Short</p><script>var x=1</script>"
        "</main></body></html>"
    )
    assert parse_job_page(html, PAGE_URL).text == "Short"


def test_trafilatura_crash_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    def _crash(*args: Any, **kwargs: Any) -> str:
        raise ValueError("bad tree")

    monkeypatch.setattr(web_job.trafilatura, "extract", _crash)
    html = "<html><body><article><p>Article text</p></article></body></html>"
    assert parse_job_page(html, PAGE_URL).text == "Article text"


def test_huge_page_skips_trafilatura(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        web_job.trafilatura, "extract", lambda *a, **k: calls.append("x") or "t"
    )
    huge = "<html><body><main>" + "<p>row</p>" * 40_000 + "</main></body></html>"

    page = parse_job_page(huge, PAGE_URL)

    assert calls == []
    assert page.text.startswith("row\nrow")
    assert parse_job_page("<main><p>small</p></main>", PAGE_URL).text == "t"


def test_text_is_capped() -> None:
    page = parse_job_page(_ld(_posting(description="a" * 50_000)), PAGE_URL)
    assert len(page.text) == MAX_TEXT_CHARS


# --- hostile / empty input ----------------------------------------------------


@pytest.mark.parametrize("html", ["", "   ", "<html></html>", "<html><body></body></html>"])
def test_empty_page_gives_empty_text(html: str) -> None:
    assert parse_job_page(html, PAGE_URL) == JobPage(
        text="", posted_at=None, title=None, company=None
    )


_DEEP_CHUNK = "<div>" * 250 + "x" + "</div>" * 250


@pytest.mark.parametrize(
    "html",
    [
        pytest.param("<div>" * 50_000 + "deep text" + "</div>" * 50_000, id="deep"),
        # ~5 MB of chunks nested 250 deep: must stay linear, not depth x size
        pytest.param(_DEEP_CHUNK * 2_000, id="many-deep-chunks"),
        pytest.param(
            _ld(_posting(description=_DEEP_CHUNK * 500)), id="deep-ld-description"
        ),
        pytest.param("<p>" * 20_000, id="unclosed"),
        pytest.param("\x00<html>\x00<body>\ud800 text</body>", id="nul-surrogate"),
        pytest.param(
            '<script type="application/ld+json">' + '{"a":' * 50_000 + "</script>",
            id="deep-json",
        ),
        pytest.param(
            _ld([{"@type": "Thing"}] * 100_000), id="huge-json-ld-array"
        ),
        pytest.param('<?xml version="1.0" encoding="utf-8"?><p>x</p>', id="xml-decl"),
        pytest.param("<<<>>><a href=<b></a>", id="garbage"),
    ],
)
def test_hostile_html_does_not_raise(html: str) -> None:
    page = parse_job_page(html, PAGE_URL)
    assert isinstance(page.text, str)
    assert len(page.text) <= MAX_TEXT_CHARS


# --- fetch_job ----------------------------------------------------------------


@pytest.fixture
async def guarded_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with make_client() as http_client:
        yield http_client


async def _public(host: str, port: int) -> list[str]:
    return [PUBLIC_IP]


@respx.mock
async def test_fetch_job_fetches_through_guard_and_parses(
    guarded_client: httpx.AsyncClient,
) -> None:
    route = respx.get(f"https://{PUBLIC_IP}/vacancy/1").respond(
        200, headers=HTML, text=_ld(_posting(description="<p>Hello</p>", title="Dev"))
    )

    page = await fetch_job(PAGE_URL, client=guarded_client, resolver=_public)

    assert (page.text, page.title) == ("Hello", "Dev")
    assert route.calls.last.request.headers["host"] == "jobs.example.com"


@respx.mock
async def test_fetch_job_propagates_page_errors(guarded_client: httpx.AsyncClient) -> None:
    respx.get(f"https://{PUBLIC_IP}/vacancy/1").respond(404, headers=HTML, text="gone")

    with pytest.raises(PageFetchError) as exc_info:
        await fetch_job(PAGE_URL, client=guarded_client, resolver=_public)
    assert exc_info.value.reason == "not_found"


async def test_fetch_job_propagates_unsafe_url(guarded_client: httpx.AsyncClient) -> None:
    async def _private(host: str, port: int) -> list[str]:
        return ["127.0.0.1"]

    with pytest.raises(UnsafeUrlError):
        await fetch_job(PAGE_URL, client=guarded_client, resolver=_private)
