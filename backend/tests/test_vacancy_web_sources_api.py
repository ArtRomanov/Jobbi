"""Web page sources: POST /vacancy-sources/preview and POST /vacancy-sources.

Every page goes through `safe_http`; the OS resolver is replaced by a stub so
no test touches real DNS, and respx answers the pinned-IP requests.
"""

import hashlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.discovery import web_scan
from app.discovery.fetchers import safe_http
from app.discovery.fetchers.web_listing import parse_listing
from app.models.vacancy import Vacancy, VacancyCardSource
from app.models.vacancy_seen_key import VacancySeenKey
from app.models.vacancy_source import VacancySource
from app.services import vacancy_source_service
from app.services.vacancy_source_parsing import (
    INVALID_INPUT_MESSAGE,
    PRIVATE_INVITE_MESSAGE,
    UNSAFE_LINK_MESSAGE,
)
from app.services.vacancy_source_service import MAX_SOURCES
from tests import conftest as root_conftest

_real_session_local = root_conftest.TestSessionLocal

URL = "/api/v1/vacancy-sources"
PREVIEW_URL = f"{URL}/preview"
PUBLIC_IP = "93.184.216.34"
HTML = {"content-type": "text/html; charset=utf-8"}
WEB_FIXTURES = Path(__file__).parent / "discovery_boards" / "fixtures" / "web"

GEEKJOB = "https://geekjob.ru/vacancies"
CANNOT_OPEN = "Could not open this page"
NO_VACANCIES = (
    "No vacancies found on this page. Check the link or set 'Job link contains'."
)
DUPLICATE = "Already in your sources"
LIMIT = f"You can watch up to {MAX_SOURCES} sources"

GEEKJOB_PAGE_2 = """<html><body><main>
<a href="/vacancy/aaa111"><h3>Page two job A</h3></a>
<a href="/vacancy/bbb222"><h3>Page two job B</h3></a>
<a href="/vacancy/6b0412760e9260dd7d039713"><h3>Repeated from page one</h3></a>
</main></body></html>"""

SMALL_LISTING = """<html><body>
<nav><a href="/vacancy/menu">Menu job</a></nav>
<a href="/vacancy/1"><h2>Backend Developer</h2></a>
<a href="/vacancy/2"><h2>Frontend Developer</h2></a>
<a href="/about/team">About us</a>
</body></html>"""

CAREERS_PAGE = """<html><body>
<a href="/careers/101-react-engineer">React Engineer</a>
<a href="/careers/102-data-analyst">Data Analyst</a>
</body></html>"""

# A career page that embeds its Greenhouse board via JS: no job links of its own.
EMBEDDED_BOARD_PAGE = """<html><body><h1>Careers</h1>
<div id="grnhse_app"></div>
<script src="https://boards.greenhouse.io/embed/job_board/js?for=acme"></script>
</body></html>"""


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _fixture(name: str) -> str:
    return (WEB_FIXTURES / f"{name}.html").read_text(encoding="utf-8")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture(autouse=True)
def _stub_network(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Resolve test hosts without DNS and skip the 1 s pause between pages."""
    resolved: list[str] = []
    table = {
        "localhost": ["127.0.0.1", "::1"],
        "intranet.example.com": ["10.0.0.5"],
        "nowhere.example.com": [],
    }

    async def _resolve(host: str, port: int) -> list[str]:
        resolved.append(host)
        if host not in table and not host.endswith(("example.com", ".ru", ".com")):
            raise OSError(f"unknown host {host}")
        return table.get(host, [PUBLIC_IP])

    monkeypatch.setattr(safe_http, "system_resolver", _resolve)
    monkeypatch.setattr(web_scan, "PAGE_PAUSE_SECONDS", 0.0)
    return resolved


@pytest.fixture
def token(registered_user: dict) -> str:
    return registered_user["access_token"]


@pytest.fixture
def user_id(registered_user: dict) -> str:
    return registered_user["user"]["id"]


def _page(
    respx_mock: respx.MockRouter, path: str, text: str, *, scheme: str = "https"
) -> respx.Route:
    return respx_mock.get(f"{scheme}://{PUBLIC_IP}{path}").respond(
        200, headers=HTML, text=text
    )


@pytest.fixture
def geekjob_page_1(respx_mock: respx.MockRouter) -> respx.Route:
    return _page(respx_mock, "/vacancies", _fixture("geekjob"))


async def _count(db: AsyncSession, model: type) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def _insert_telegram(db: AsyncSession, user_id: str, handle: str) -> str:
    source = VacancySource(
        user_id=user_id,
        kind="telegram",
        handle=handle,
        default_name=f"@{handle}",
        display_name=f"@{handle}",
    )
    db.add(source)
    await db.commit()
    return source.id


async def _insert_web(db: AsyncSession, user_id: str, url: str) -> str:
    source = VacancySource(
        user_id=user_id,
        kind="web",
        handle="placeholder",
        url=url,
        url_hash=_sha(url),
        default_name="geekjob.ru",
        display_name="geekjob.ru",
    )
    db.add(source)
    await db.flush()
    source.handle = source.id
    await db.commit()
    return source.id


# --- preview: web pages -------------------------------------------------------------


async def test_preview_counts_page_one_and_lists_five_titles_in_order(
    client: httpx.AsyncClient, token: str, geekjob_page_1: respx.Route
) -> None:
    resp = await client.post(PREVIEW_URL, json={"input": GEEKJOB}, headers=_auth(token))

    assert resp.status_code == 200
    expected = parse_listing(_fixture("geekjob"), GEEKJOB, None).jobs
    assert resp.json() == {
        "kind": "web",
        "default_name": "geekjob.ru",
        "found_count": 20,
        "titles": [job.title for job in expected[:5]],
        "ats_hint": None,
    }
    assert resp.json()["titles"][0] == "Product Design Lead в Core Product"
    # Page 1 only, pinned to the checked IP with the real host name.
    assert geekjob_page_1.call_count == 1
    assert geekjob_page_1.calls.last.request.headers["host"] == "geekjob.ru"


async def test_preview_returns_the_ats_hint_without_fetching_the_board(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    page = _page(respx_mock, "/jobs", _fixture("wrike"))

    resp = await client.post(
        PREVIEW_URL, json={"input": "https://www.wrike.com/jobs/"}, headers=_auth(token)
    )

    assert resp.status_code == 200
    assert resp.json()["ats_hint"] == {
        "kind": "greenhouse",
        "input": "https://job-boards.greenhouse.io/wrike",
        "label": "Greenhouse",
    }
    # Only the page itself was requested (respx fails on any unmocked call).
    assert page.call_count == 1
    assert len(respx_mock.calls) == 1


async def test_preview_default_name_drops_www(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    _page(respx_mock, "/jobs", SMALL_LISTING)

    resp = await client.post(
        PREVIEW_URL, json={"input": "WWW.Example.com/jobs/"}, headers=_auth(token)
    )

    assert resp.status_code == 200
    assert resp.json()["default_name"] == "example.com"
    assert resp.json()["titles"] == ["Backend Developer", "Frontend Developer"]


async def test_preview_applies_job_link_contains(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    _page(respx_mock, "/jobs", SMALL_LISTING)

    resp = await client.post(
        PREVIEW_URL,
        json={"input": "https://example.com/jobs", "job_link_contains": "  /about/ "},
        headers=_auth(token),
    )

    assert resp.status_code == 200
    assert resp.json()["found_count"] == 1
    assert resp.json()["titles"] == ["About us"]


async def test_clever_careers_is_a_web_page(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    _page(respx_mock, "/careers", CAREERS_PAGE)

    resp = await client.post(
        PREVIEW_URL, json={"input": "clever.com/careers"}, headers=_auth(token)
    )

    assert resp.status_code == 200
    assert resp.json()["kind"] == "web"
    assert resp.json()["default_name"] == "clever.com"
    assert resp.json()["found_count"] == 2


async def test_preview_page_without_vacancies(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    _page(respx_mock, "/", _fixture("hirehi"))

    resp = await client.post(
        PREVIEW_URL, json={"input": "https://hirehi.ru/"}, headers=_auth(token)
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": NO_VACANCIES}


async def test_preview_without_vacancies_but_with_board_link_returns_hint(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    page = _page(respx_mock, "/careers", EMBEDDED_BOARD_PAGE)

    resp = await client.post(
        PREVIEW_URL, json={"input": "https://acme.com/careers"}, headers=_auth(token)
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "kind": "web",
        "default_name": "acme.com",
        "found_count": 0,
        "titles": [],
        "ats_hint": {
            "kind": "greenhouse",
            "input": "https://job-boards.greenhouse.io/acme",
            "label": "Greenhouse",
        },
    }
    # The board itself is not fetched.
    assert page.call_count == 1
    assert len(respx_mock.calls) == 1


async def test_preview_without_vacancies_or_board_link_is_400(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    _page(respx_mock, "/careers", "<html><body><h1>Careers</h1></body></html>")

    resp = await client.post(
        PREVIEW_URL, json={"input": "https://acme.com/careers"}, headers=_auth(token)
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": NO_VACANCIES}


async def test_save_without_vacancies_but_with_board_link_is_400(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
) -> None:
    _page(respx_mock, "/careers", EMBEDDED_BOARD_PAGE)

    resp = await client.post(
        URL, json={"input": "https://acme.com/careers"}, headers=_auth(token)
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": NO_VACANCIES}
    assert await _count(db_session, VacancySource) == 0


@pytest.mark.parametrize(
    "raw",
    [
        "http://localhost:8003/",
        "http://localhost/",
        "http://192.168.1.1/",
        "http://127.0.0.1/jobs",
        "https://[::1]/jobs",
        "https://169.254.169.254/latest/meta-data",
        "https://intranet.example.com/jobs",  # resolves to 10.0.0.5
        "https://example.com:8443/jobs",
        "file:///etc/passwd",
        "ftp://example.com/jobs",
        "javascript:alert(1)",
    ],
)
async def test_preview_refuses_local_and_non_http_links(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
    raw: str,
) -> None:
    resp = await client.post(PREVIEW_URL, json={"input": raw}, headers=_auth(token))

    assert resp.status_code == 400
    assert resp.json() == {"detail": UNSAFE_LINK_MESSAGE}
    assert not respx_mock.calls  # never opened
    assert await _count(db_session, VacancySource) == 0


async def test_preview_refuses_redirect_to_private_address(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"https://{PUBLIC_IP}/jobs").respond(
        302, headers={"location": "http://127.0.0.1/admin"}
    )

    resp = await client.post(
        PREVIEW_URL, json={"input": "https://example.com/jobs"}, headers=_auth(token)
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": UNSAFE_LINK_MESSAGE}
    assert len(respx_mock.calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(404),
        httpx.Response(403),
        httpx.Response(200, headers={"content-type": "application/json"}, json={}),
        httpx.Response(
            200, headers={**HTML, "content-length": "999999999"}, text="<html></html>"
        ),
        httpx.ConnectError("boom"),
        httpx.ReadTimeout("slow"),
    ],
    ids=["500", "404", "403", "not-html", "too-large", "connect-error", "timeout"],
)
async def test_preview_unreadable_page(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    response: httpx.Response | Exception,
) -> None:
    respx_mock.get(f"https://{PUBLIC_IP}/jobs").mock(side_effect=[response])

    resp = await client.post(
        PREVIEW_URL, json={"input": "https://example.com/jobs"}, headers=_auth(token)
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": CANNOT_OPEN}


@pytest.mark.parametrize(
    "raw", ["https://no-such-site.invalid/jobs", "https://nowhere.example.com/jobs"]
)
async def test_preview_unresolvable_host(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter, raw: str
) -> None:
    resp = await client.post(PREVIEW_URL, json={"input": raw}, headers=_auth(token))

    assert resp.status_code == 400
    assert resp.json() == {"detail": CANNOT_OPEN}
    assert not respx_mock.calls


async def test_preview_never_writes(
    client: httpx.AsyncClient,
    token: str,
    geekjob_page_1: respx.Route,
    db_session: AsyncSession,
) -> None:
    for _ in range(2):
        resp = await client.post(
            PREVIEW_URL, json={"input": GEEKJOB}, headers=_auth(token)
        )
        assert resp.status_code == 200

    assert await _count(db_session, VacancySource) == 0
    assert await _count(db_session, VacancySeenKey) == 0
    assert await _count(db_session, Vacancy) == 0


@pytest.mark.parametrize(
    "pattern", ["x" * 101, "/vac\x00ancy/"], ids=["too-long", "control-char"]
)
async def test_preview_rejects_bad_job_link_contains(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter, pattern: str
) -> None:
    resp = await client.post(
        PREVIEW_URL,
        json={"input": GEEKJOB, "job_link_contains": pattern},
        headers=_auth(token),
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": "'Job link contains' must be 1–100 characters"}
    assert not respx_mock.calls


async def test_preview_accepts_pattern_of_100_chars_and_blank_pattern(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    _page(respx_mock, "/vacancies", _fixture("geekjob"))

    long_pattern = await client.post(
        PREVIEW_URL,
        json={"input": GEEKJOB, "job_link_contains": "x" * 100},
        headers=_auth(token),
    )
    blank = await client.post(
        PREVIEW_URL,
        json={"input": GEEKJOB, "job_link_contains": "   "},
        headers=_auth(token),
    )

    assert long_pattern.status_code == 400
    assert long_pattern.json() == {"detail": NO_VACANCIES}  # valid, just no match
    assert blank.status_code == 200
    assert blank.json()["found_count"] == 20


# --- preview: other kinds -------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "kind"),
    [
        ("@durov_jobs", "telegram"),
        ("https://t.me/s/durov_jobs", "telegram"),
        ("https://boards.greenhouse.io/acme", "greenhouse"),
        ("https://jobs.eu.lever.co/acme", "lever_eu"),
        ("approvalmax.teamtailor.com", "teamtailor"),
    ],
)
async def test_preview_non_web_returns_kind_only_without_network(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    _stub_network: list[str],
    raw: str,
    kind: str,
) -> None:
    resp = await client.post(PREVIEW_URL, json={"input": raw}, headers=_auth(token))

    assert resp.status_code == 200
    assert resp.json() == {"kind": kind}
    assert not respx_mock.calls
    assert _stub_network == []


async def test_preview_bad_input_keeps_telegram_hint(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    resp = await client.post(PREVIEW_URL, json={"input": "@abc"}, headers=_auth(token))

    assert resp.status_code == 400
    assert resp.json() == {
        "detail": "Enter a Telegram channel as @name or a t.me/name link"
    }


# --- preview: duplicates, limit, source_id -----------------------------------------


@pytest.mark.parametrize(
    "variant",
    [
        GEEKJOB,
        f"{GEEKJOB}/",
        "https://GeekJob.RU/vacancies",
        f"{GEEKJOB}?utm_source=telegram&utm_medium=post",
        f"{GEEKJOB}#top",
        "geekjob.ru/vacancies",
        "https://geekjob.ru:443/vacancies",
    ],
)
async def test_preview_duplicate_by_normalized_url(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
    variant: str,
) -> None:
    await _insert_web(db_session, user_id, GEEKJOB)

    resp = await client.post(PREVIEW_URL, json={"input": variant}, headers=_auth(token))

    assert resp.status_code == 409
    assert resp.json() == {"detail": DUPLICATE}
    assert not respx_mock.calls


async def test_preview_excludes_the_edited_source_from_duplicate_check(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    geekjob_page_1: respx.Route,
    db_session: AsyncSession,
) -> None:
    source_id = await _insert_web(db_session, user_id, GEEKJOB)

    resp = await client.post(
        PREVIEW_URL,
        json={"input": GEEKJOB, "source_id": source_id},
        headers=_auth(token),
    )

    assert resp.status_code == 200


async def test_preview_limit_and_edit_exclusion(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    geekjob_page_1: respx.Route,
    db_session: AsyncSession,
) -> None:
    ids = [
        await _insert_telegram(db_session, user_id, f"chan_{i:02d}")
        for i in range(MAX_SOURCES)
    ]

    full = await client.post(PREVIEW_URL, json={"input": GEEKJOB}, headers=_auth(token))
    editing = await client.post(
        PREVIEW_URL, json={"input": GEEKJOB, "source_id": ids[0]}, headers=_auth(token)
    )

    assert full.status_code == 400
    assert full.json() == {"detail": LIMIT}
    assert editing.status_code == 200
    assert geekjob_page_1.call_count == 1


async def test_preview_source_id_of_another_user_is_not_found(
    client: httpx.AsyncClient,
    token: str,
    other_registered_user: dict,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
) -> None:
    other_id = other_registered_user["user"]["id"]
    foreign = await _insert_web(db_session, other_id, GEEKJOB)

    resp = await client.post(
        PREVIEW_URL, json={"input": GEEKJOB, "source_id": foreign}, headers=_auth(token)
    )

    assert resp.status_code == 404
    assert not respx_mock.calls


async def test_preview_requires_auth(client: httpx.AsyncClient) -> None:
    resp = await client.post(PREVIEW_URL, json={"input": GEEKJOB})
    assert resp.status_code in (401, 403)


# --- save -------------------------------------------------------------------------


async def test_save_records_every_listed_job_across_pages_as_seen(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
) -> None:
    page_1 = _page(respx_mock, "/vacancies", _fixture("geekjob"))
    page_2 = _page(respx_mock, "/vacancies/2", GEEKJOB_PAGE_2)

    resp = await client.post(
        URL,
        json={"input": f"{GEEKJOB}/?utm_source=x", "job_link_contains": " /vacancy/ "},
        headers=_auth(token),
    )

    assert resp.status_code == 201
    data = resp.json()
    source_id = data["id"]
    assert data["kind"] == "web"
    assert data["key"] == f"web:{source_id}"
    assert data["display_name"] == "geekjob.ru"
    assert data["url"] == GEEKJOB
    assert data["job_link_contains"] == "/vacancy/"
    assert data["scanning"] is False
    assert data["watching_since"] is not None
    assert data["last_checked_at"] == data["watching_since"]
    assert (page_1.call_count, page_2.call_count) == (1, 1)

    source = await db_session.get(VacancySource, source_id)
    assert source is not None
    assert source.handle == source_id
    assert source.url_hash == _sha(GEEKJOB)
    assert source.initial_scan_completed_at is not None

    page_1_urls = [
        job.url for job in parse_listing(_fixture("geekjob"), GEEKJOB, "/vacancy/").jobs
    ]
    listed = [
        *page_1_urls,
        "https://geekjob.ru/vacancy/aaa111",
        "https://geekjob.ru/vacancy/bbb222",
    ]
    rows = (
        await db_session.execute(
            select(VacancySeenKey.external_key, VacancySeenKey.evaluated_at).where(
                VacancySeenKey.user_id == user_id
            )
        )
    ).all()
    assert len(rows) == len(listed) == 22
    assert {key for key, _ in rows} == {
        f"web:{source_id}/{_sha(url)}" for url in listed
    }
    assert all(evaluated_at is None for _, evaluated_at in rows)
    assert await _count(db_session, Vacancy) == 0  # nothing reaches the Inbox

    listed_sources = (await client.get(URL, headers=_auth(token))).json()["sources"]
    assert listed_sources == [data]


async def test_save_reads_at_most_five_pages(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    def page(n: int) -> str:
        return (
            f'<html><body><a href="/vacancy/p{n}"><h3>Job {n}</h3></a>'
            f'<a rel="next" href="/jobs?page={n + 1}">next</a></body></html>'
        )

    respx_mock.get(f"https://{PUBLIC_IP}/jobs").mock(
        side_effect=lambda request: httpx.Response(
            200,
            headers=HTML,
            text=page(int(request.url.params.get("page", "1"))),
        )
    )

    resp = await client.post(
        URL, json={"input": "https://example.com/jobs"}, headers=_auth(token)
    )

    assert resp.status_code == 201
    assert len(respx_mock.calls) == 5


async def test_save_keeps_pages_read_before_a_later_page_fails(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
) -> None:
    _page(respx_mock, "/vacancies", _fixture("geekjob"))
    respx_mock.get(f"https://{PUBLIC_IP}/vacancies/2").respond(503)

    resp = await client.post(URL, json={"input": GEEKJOB}, headers=_auth(token))

    assert resp.status_code == 201
    assert await _count(db_session, VacancySeenKey) == 20


async def test_save_uses_trimmed_custom_name(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    _page(respx_mock, "/jobs", SMALL_LISTING)

    resp = await client.post(
        URL,
        json={"input": "https://example.com/jobs", "name": "  Example — remote  "},
        headers=_auth(token),
    )

    assert resp.status_code == 201
    assert resp.json()["display_name"] == "Example — remote"


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"name": "x" * 101}, "Name can be up to 100 characters"),
        (
            {"job_link_contains": "y" * 101},
            "'Job link contains' must be 1–100 characters",
        ),
    ],
)
async def test_save_rejects_long_name_or_pattern_before_network(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
    body: dict[str, str],
    detail: str,
) -> None:
    resp = await client.post(
        URL, json={"input": "https://example.com/jobs", **body}, headers=_auth(token)
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": detail}
    assert not respx_mock.calls
    assert await _count(db_session, VacancySource) == 0


async def test_save_name_of_100_chars_is_accepted(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    _page(respx_mock, "/jobs", SMALL_LISTING)

    resp = await client.post(
        URL,
        json={"input": "https://example.com/jobs", "name": "n" * 100},
        headers=_auth(token),
    )

    assert resp.status_code == 201
    assert resp.json()["display_name"] == "n" * 100


@pytest.mark.parametrize(
    ("raw", "route_text", "detail"),
    [
        ("https://hirehi.ru/", "hirehi", NO_VACANCIES),
        ("http://192.168.1.1/", None, UNSAFE_LINK_MESSAGE),
        ("file:///etc/passwd", None, UNSAFE_LINK_MESSAGE),
    ],
)
async def test_save_errors_save_nothing(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
    raw: str,
    route_text: str | None,
    detail: str,
) -> None:
    if route_text is not None:
        _page(respx_mock, "/", _fixture(route_text))

    resp = await client.post(URL, json={"input": raw}, headers=_auth(token))

    assert resp.status_code == 400
    assert resp.json() == {"detail": detail}
    assert await _count(db_session, VacancySource) == 0
    assert await _count(db_session, VacancySeenKey) == 0


async def test_save_unreadable_page(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
) -> None:
    respx_mock.get(f"https://{PUBLIC_IP}/jobs").mock(
        side_effect=httpx.ConnectError("down")
    )

    resp = await client.post(
        URL, json={"input": "https://example.com/jobs"}, headers=_auth(token)
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": CANNOT_OPEN}
    assert await _count(db_session, VacancySource) == 0


@pytest.mark.parametrize(
    "variant",
    [
        f"{GEEKJOB}/",
        "https://GEEKJOB.ru/vacancies",
        f"{GEEKJOB}?utm_source=tg&utm_campaign=x",
        "geekjob.ru/vacancies/",
    ],
)
async def test_save_duplicate_by_normalized_url(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
    variant: str,
) -> None:
    page_1 = _page(respx_mock, "/vacancies", _fixture("geekjob"))
    respx_mock.get(f"https://{PUBLIC_IP}/vacancies/2").respond(404)
    first = await client.post(URL, json={"input": GEEKJOB}, headers=_auth(token))
    assert first.status_code == 201
    calls = page_1.call_count

    resp = await client.post(URL, json={"input": variant}, headers=_auth(token))

    assert resp.status_code == 409
    assert resp.json() == {"detail": DUPLICATE}
    assert page_1.call_count == calls  # rejected before the network
    assert await _count(db_session, VacancySource) == 1


async def test_same_site_with_other_filters_is_a_different_source(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"https://{PUBLIC_IP}/jobs").respond(
        200, headers=HTML, text=SMALL_LISTING
    )

    react = await client.post(
        URL, json={"input": "https://example.com/jobs?q=react"}, headers=_auth(token)
    )
    vue = await client.post(
        URL, json={"input": "https://example.com/jobs?q=vue"}, headers=_auth(token)
    )

    assert (react.status_code, vue.status_code) == (201, 201)
    assert react.json()["display_name"] == vue.json()["display_name"] == "example.com"


async def test_save_unique_constraint_maps_to_conflict(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    geekjob_page_1: respx.Route,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If both checks miss a duplicate, the url_hash constraint still answers 409."""
    respx_mock.get(f"https://{PUBLIC_IP}/vacancies/2").respond(404)
    await _insert_web(db_session, user_id, GEEKJOB)

    async def _never_exists(*_: object) -> bool:
        return False

    monkeypatch.setattr(vacancy_source_service, "_source_exists", _never_exists)

    resp = await client.post(URL, json={"input": GEEKJOB}, headers=_auth(token))

    assert resp.status_code == 409
    assert resp.json() == {"detail": DUPLICATE}
    assert await _count(db_session, VacancySource) == 1
    assert await _count(db_session, VacancySeenKey) == 0


async def test_save_limit_counts_web_and_other_sources(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
) -> None:
    for i in range(MAX_SOURCES - 1):
        await _insert_telegram(db_session, user_id, f"chan_{i:02d}")
    await _insert_web(db_session, user_id, "https://example.com/other")

    resp = await client.post(URL, json={"input": GEEKJOB}, headers=_auth(token))

    assert resp.status_code == 400
    assert resp.json() == {"detail": LIMIT}
    assert not respx_mock.calls


async def test_web_sources_are_per_user(
    client: httpx.AsyncClient,
    token: str,
    other_registered_user: dict,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
) -> None:
    other_id = other_registered_user["user"]["id"]
    await _insert_web(db_session, other_id, GEEKJOB)
    _page(respx_mock, "/vacancies", _fixture("geekjob"))
    respx_mock.get(f"https://{PUBLIC_IP}/vacancies/2").respond(404)

    preview = await client.post(
        PREVIEW_URL, json={"input": GEEKJOB}, headers=_auth(token)
    )
    saved = await client.post(URL, json={"input": GEEKJOB}, headers=_auth(token))

    assert preview.status_code == 200
    assert saved.status_code == 201
    mine = (await client.get(URL, headers=_auth(token))).json()["sources"]
    assert [s["id"] for s in mine] == [saved.json()["id"]]
    theirs = (
        await client.get(URL, headers=_auth(other_registered_user["access_token"]))
    ).json()["sources"]
    assert saved.json()["id"] not in [s["id"] for s in theirs]


async def test_non_web_save_ignores_web_only_fields(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get("https://boards-api.greenhouse.io/v1/boards/acme").respond(
        200, json={"name": "Acme Corp", "content": ""}
    )

    resp = await client.post(
        URL,
        json={
            "input": "https://boards.greenhouse.io/acme",
            "job_link_contains": "/jobs/",
            "name": "My Acme",
        },
        headers=_auth(token),
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["display_name"] == "Acme Corp"
    assert (data["url"], data["job_link_contains"], data["watching_since"]) == (
        None,
        None,
        None,
    )
    assert data["scanning"] is True


# --- edit (PATCH) -------------------------------------------------------------------

EXAMPLE_JOBS = "https://example.com/jobs"
BUSY = "This source is being scanned — try again in a moment"

REACT_LISTING = """<html><body>
<a href="/vacancy/r1"><h2>React Developer</h2></a>
<a href="/vacancy/r2"><h2>Senior React Engineer</h2></a>
</body></html>"""

VUE_LISTING = """<html><body>
<a href="/vacancy/v1"><h2>Vue Developer</h2></a>
<a href="/vacancy/r2"><h2>Senior React Engineer</h2></a>
</body></html>"""


async def _patch(
    client: httpx.AsyncClient, token: str, source_id: str, body: dict
) -> httpx.Response:
    return await client.patch(f"{URL}/{source_id}", json=body, headers=_auth(token))


async def _add_pending(
    db: AsyncSession,
    user_id: str,
    source_id: str,
    key: str,
    *,
    state: str = "pending",
    needs_detail: bool = True,
) -> str:
    card = Vacancy(
        user_id=user_id,
        source_id=source_id,
        external_key=f"web:{source_id}/{key}",
        url=f"https://example.com/vacancy/{key}",
        job_link=f"https://example.com/vacancy/{key}",
        title=f"Job {key}",
        text=f"Job {key}",
        posted_at=datetime(2026, 11, 20, 12, 0),
        state=state,
        fit=None if state == "pending" else "medium",
        needs_detail=needs_detail,
    )
    db.add(card)
    await db.flush()
    db.add(
        VacancyCardSource(
            vacancy_id=card.id,
            source_id=source_id,
            source_kind="web",
            source_handle=source_id,
            label="example.com",
        )
    )
    await db.commit()
    return card.id


async def _seen(db: AsyncSession, user_id: str) -> set[str]:
    rows = await db.execute(
        select(VacancySeenKey.external_key).where(VacancySeenKey.user_id == user_id)
    )
    return set(rows.scalars().all())


async def _source_row(db: AsyncSession, source_id: str) -> VacancySource | None:
    db.expire_all()
    return await db.get(VacancySource, source_id)


def _job_key(source_id: str, path: str) -> str:
    return f"web:{source_id}/{_sha(f'https://example.com{path}')}"


async def test_edit_pattern_keeps_history_and_drops_pending_rows(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
) -> None:
    page = _page(respx_mock, "/jobs", SMALL_LISTING)
    added = await client.post(URL, json={"input": EXAMPLE_JOBS}, headers=_auth(token))
    source_id = added.json()["id"]
    history = await _seen(db_session, user_id)
    assert history
    pending_id = await _add_pending(db_session, user_id, source_id, "p1")
    waiting_id = await _add_pending(
        db_session, user_id, source_id, "p2", needs_detail=False
    )
    card_id = await _add_pending(db_session, user_id, source_id, "c1", state="new")

    resp = await _patch(client, token, source_id, {"job_link_contains": " /about/ "})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert (data["id"], data["key"]) == (source_id, f"web:{source_id}")
    assert (data["url"], data["job_link_contains"]) == (EXAMPLE_JOBS, "/about/")
    assert data["editable"] is True
    source = await _source_row(db_session, source_id)
    assert source is not None and source.revision == 1
    # Old history stays; what the new filter lists now is remembered too.
    assert await _seen(db_session, user_id) == history | {
        _job_key(source_id, "/about/team")
    }
    assert await db_session.get(Vacancy, pending_id) is None
    assert await db_session.get(Vacancy, waiting_id) is None
    card = await db_session.get(Vacancy, card_id)
    assert card is not None and card.source_id == source_id
    links = await db_session.execute(
        select(VacancyCardSource.vacancy_id).where(
            VacancyCardSource.source_id == source_id
        )
    )
    assert list(links.scalars().all()) == [card_id]

    # The same pattern again (after trimming) changes nothing and reads nothing.
    calls = page.call_count
    again = await _patch(client, token, source_id, {"job_link_contains": "/about/"})
    assert again.status_code == 200
    assert page.call_count == calls
    source = await _source_row(db_session, source_id)
    assert source is not None and source.revision == 1


async def test_edit_url_react_to_vue_leaves_no_old_filter_pending_rows(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
) -> None:
    jobs = f"https://{PUBLIC_IP}/jobs"
    react = respx_mock.get(jobs, params={"q": "react"}).respond(
        200, headers=HTML, text=REACT_LISTING
    )
    vue = respx_mock.get(jobs, params={"q": "vue"}).respond(
        200, headers=HTML, text=VUE_LISTING
    )
    added = await client.post(
        URL,
        json={"input": f"{EXAMPLE_JOBS}?q=react", "name": "My search"},
        headers=_auth(token),
    )
    assert added.status_code == 201, added.text
    source_id = added.json()["id"]
    await _add_pending(db_session, user_id, source_id, "r3")

    resp = await _patch(client, token, source_id, {"input": f"{EXAMPLE_JOBS}?q=vue"})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == source_id
    assert data["url"] == f"{EXAMPLE_JOBS}?q=vue"
    assert data["display_name"] == "My search"  # the custom name is kept
    assert (react.call_count, vue.call_count) == (1, 1)
    pending = await db_session.execute(
        select(func.count())
        .select_from(Vacancy)
        .where(Vacancy.source_id == source_id, Vacancy.state == "pending")
    )
    assert pending.scalar_one() == 0
    assert await _seen(db_session, user_id) == {
        _job_key(source_id, f"/vacancy/{key}") for key in ("r1", "r2", "v1")
    }
    source = await _source_row(db_session, source_id)
    assert source is not None
    assert (source.url_hash, source.revision) == (_sha(f"{EXAMPLE_JOBS}?q=vue"), 1)


async def test_edit_url_with_blank_name_uses_the_new_default_name(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
) -> None:
    _page(respx_mock, "/jobs", SMALL_LISTING)
    _page(respx_mock, "/careers", CAREERS_PAGE)
    added = await client.post(
        URL, json={"input": EXAMPLE_JOBS, "name": "Old"}, headers=_auth(token)
    )
    source_id = added.json()["id"]

    resp = await _patch(
        client, token, source_id, {"input": "clever.com/careers", "name": " "}
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert (data["display_name"], data["name_is_custom"]) == ("clever.com", False)
    assert data["id"] == source_id


async def test_edit_lever_to_web_replaces_the_source(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
) -> None:
    _page(respx_mock, "/jobs", SMALL_LISTING)
    lever = VacancySource(
        user_id=user_id,
        kind="lever",
        handle="acme-labs",
        default_name="Acme Labs",
        display_name="Acme Labs",
    )
    db_session.add(lever)
    await db_session.commit()
    old_id = lever.id
    card = Vacancy(
        user_id=user_id,
        source_id=old_id,
        external_key="lever:acme-labs/1",
        url="https://jobs.lever.co/acme-labs/1",
        job_link="https://jobs.lever.co/acme-labs/1",
        text="Dev",
        posted_at=datetime(2026, 11, 20, 12, 0),
        state="new",
        fit="high",
    )
    db_session.add(card)
    await db_session.flush()
    db_session.add(
        VacancyCardSource(
            vacancy_id=card.id,
            source_id=old_id,
            source_kind="lever",
            source_handle="acme-labs",
            label="Acme Labs",
        )
    )
    await db_session.commit()

    resp = await _patch(
        client,
        token,
        old_id,
        {"input": EXAMPLE_JOBS, "job_link_contains": "/vacancy/", "name": "Acme web"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    new_id = data["id"]
    assert new_id != old_id
    assert (data["kind"], data["key"]) == ("web", f"web:{new_id}")
    assert (data["display_name"], data["job_link_contains"]) == (
        "Acme web",
        "/vacancy/",
    )
    assert data["scanning"] is False
    assert await _source_row(db_session, old_id) is None
    seen = await _seen(db_session, user_id)
    assert {_job_key(new_id, "/vacancy/1"), _job_key(new_id, "/vacancy/2")} <= seen
    assert all(key.startswith(f"web:{new_id}/") for key in seen)
    body = (await client.get(URL, headers=_auth(token))).json()
    assert [s["id"] for s in body["sources"]] == [new_id]
    assert body["removed_sources"] == [
        {"key": "lever:acme-labs", "label": "Acme Labs"}
    ]


async def test_edit_web_to_board_gets_a_normal_first_scan(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
) -> None:
    respx_mock.get("https://boards-api.greenhouse.io/v1/boards/acme").respond(
        200, json={"name": "Acme Corp", "content": ""}
    )
    source_id = await _insert_web(db_session, user_id, GEEKJOB)

    resp = await _patch(
        client, token, source_id, {"input": "https://boards.greenhouse.io/acme"}
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] != source_id
    assert (data["kind"], data["display_name"]) == ("greenhouse", "Acme Corp")
    assert data["scanning"] is True
    assert (data["url"], data["job_link_contains"]) == (None, None)
    assert await _count(db_session, VacancySource) == 1


async def test_edit_and_replace_at_exactly_the_source_limit(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
) -> None:
    _page(respx_mock, "/jobs", SMALL_LISTING)
    _page(respx_mock, "/careers", CAREERS_PAGE)
    tg_ids = [
        await _insert_telegram(db_session, user_id, f"chan_{i:02d}")
        for i in range(MAX_SOURCES - 1)
    ]
    web_id = await _insert_web(db_session, user_id, EXAMPLE_JOBS)

    edited = await _patch(client, token, web_id, {"job_link_contains": "/vacancy/"})
    replaced = await _patch(client, token, tg_ids[0], {"input": "clever.com/careers"})
    preview = await client.post(
        PREVIEW_URL,
        json={"input": "https://example.com/careers", "source_id": web_id},
        headers=_auth(token),
    )

    assert edited.status_code == 200, edited.text
    assert replaced.status_code == 200, replaced.text
    assert preview.status_code == 200, preview.text
    assert await _count(db_session, VacancySource) == MAX_SOURCES


async def test_edit_to_another_sources_link_is_409(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
) -> None:
    react_id = await _insert_web(db_session, user_id, f"{EXAMPLE_JOBS}?q=react")
    await _insert_web(db_session, user_id, f"{EXAMPLE_JOBS}?q=vue")
    tg_id = await _insert_telegram(db_session, user_id, "durov_jobs")

    web = await _patch(
        client, token, react_id, {"input": "example.com/jobs/?q=vue&utm_source=x"}
    )
    kind_change = await _patch(client, token, tg_id, {"input": f"{EXAMPLE_JOBS}?q=vue"})

    assert (web.status_code, kind_change.status_code) == (409, 409)
    assert web.json() == kind_change.json() == {"detail": DUPLICATE}
    assert not respx_mock.calls
    source = await _source_row(db_session, react_id)
    assert source is not None and source.url == f"{EXAMPLE_JOBS}?q=react"
    assert await _count(db_session, VacancySource) == 3


async def test_edit_refused_while_a_first_scan_attempt_runs(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
) -> None:
    _page(respx_mock, "/jobs", SMALL_LISTING)
    tg_id = await _insert_telegram(db_session, user_id, "durov_jobs")
    source = await _source_row(db_session, tg_id)
    assert source is not None
    now = datetime.now(UTC).replace(tzinfo=None)
    source.initial_attempt_started_at = now - timedelta(minutes=1)
    await db_session.commit()

    listed = (await client.get(URL, headers=_auth(token))).json()["sources"]
    busy_link = await _patch(client, token, tg_id, {"input": EXAMPLE_JOBS})
    busy_name = await _patch(client, token, tg_id, {"name": "Mine"})

    assert listed[0]["editable"] is False
    assert (busy_link.status_code, busy_name.status_code) == (409, 409)
    assert busy_link.json() == busy_name.json() == {"detail": BUSY}
    assert not respx_mock.calls

    # A lease older than 10 minutes belongs to a crashed worker: ignored.
    source = await _source_row(db_session, tg_id)
    assert source is not None
    source.initial_attempt_started_at = now - timedelta(minutes=11)
    await db_session.commit()

    listed = (await client.get(URL, headers=_auth(token))).json()["sources"]
    ok = await _patch(client, token, tg_id, {"input": EXAMPLE_JOBS})

    assert listed[0]["editable"] is True
    assert ok.status_code == 200, ok.text
    assert ok.json()["kind"] == "web"
    assert ok.json()["editable"] is True


@pytest.mark.parametrize(
    ("body", "route_text", "detail"),
    [
        ({"input": "http://localhost/jobs"}, None, UNSAFE_LINK_MESSAGE),
        ({"input": "file:///etc/passwd"}, None, UNSAFE_LINK_MESSAGE),
        (
            {"input": "https://example.com/"},
            "<html><body>Hi</body></html>",
            NO_VACANCIES,
        ),
        (
            {"input": "https://example.com/", "job_link_contains": "y" * 101},
            None,
            "'Job link contains' must be 1–100 characters",
        ),
        (
            {"input": "https://example.com/", "name": "x" * 101},
            None,
            "Name can be up to 100 characters",
        ),
        ({"input": "t.me/joinchat/xyz"}, None, PRIVATE_INVITE_MESSAGE),
        ({"input": "t.me/ab"}, None, INVALID_INPUT_MESSAGE),
    ],
)
async def test_edit_errors_match_add_and_change_nothing(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
    body: dict,
    route_text: str | None,
    detail: str,
) -> None:
    if route_text is not None:
        _page(respx_mock, "/", route_text)
    source_id = await _insert_web(db_session, user_id, GEEKJOB)
    added = await client.post(URL, json=body, headers=_auth(token))

    resp = await _patch(client, token, source_id, body)

    assert resp.status_code == added.status_code == 400
    assert resp.json() == added.json() == {"detail": detail}
    source = await _source_row(db_session, source_id)
    assert source is not None
    assert (source.url, source.revision) == (GEEKJOB, 0)
    assert await _count(db_session, VacancySource) == 1


async def test_edit_unreadable_page_is_400_like_add(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
) -> None:
    respx_mock.get(f"https://{PUBLIC_IP}/jobs").mock(
        side_effect=httpx.ConnectError("down")
    )
    source_id = await _insert_web(db_session, user_id, GEEKJOB)

    resp = await _patch(client, token, source_id, {"input": EXAMPLE_JOBS})

    assert resp.status_code == 400
    assert resp.json() == {"detail": CANNOT_OPEN}
    source = await _source_row(db_session, source_id)
    assert source is not None and source.url == GEEKJOB


async def test_edit_another_users_source_is_404(
    client: httpx.AsyncClient,
    token: str,
    other_registered_user: dict,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
) -> None:
    other_id = other_registered_user["user"]["id"]
    foreign = await _insert_web(db_session, other_id, GEEKJOB)

    resp = await _patch(
        client, token, foreign, {"input": EXAMPLE_JOBS, "job_link_contains": "/v/"}
    )

    assert resp.status_code == 404
    assert not respx_mock.calls
    source = await _source_row(db_session, foreign)
    assert source is not None and source.url == GEEKJOB


# --- edits racing the worker or another tab (pre-merge findings) --------------------

SessionChange = Callable[[AsyncSession], Awaitable[None]]


def _during_fetch(monkeypatch: pytest.MonkeyPatch, change: SessionChange) -> None:
    """Run `change` in another session while the edit reads the new link."""
    real_listing = vacancy_source_service.read_web_listing

    async def listing(*args: Any, **kwargs: Any) -> Any:
        result = await real_listing(*args, **kwargs)
        async with _real_session_local() as other:
            await change(other)
        return result

    async def name(*args: Any, **kwargs: Any) -> str:
        async with _real_session_local() as other:
            await change(other)
        return "Durov jobs"

    monkeypatch.setattr(vacancy_source_service, "read_web_listing", listing)
    monkeypatch.setattr(vacancy_source_service, "_fetch_display_name", name)


def _update_source(source_id: str, **values: Any) -> SessionChange:
    async def change(other: AsyncSession) -> None:
        source = await other.get(VacancySource, source_id)
        assert source is not None
        for column, value in values.items():
            setattr(source, column, value)
        await other.commit()

    return change


@pytest.mark.parametrize(
    ("kind", "body"),
    [
        ("web", {"input": EXAMPLE_JOBS}),  # web edit in place
        ("telegram", {"input": EXAMPLE_JOBS}),  # replace by a web page
        ("web", {"input": "@durov_jobs"}),  # replace by a channel
    ],
)
async def test_lease_taken_during_the_fetch_is_409(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    body: dict,
) -> None:
    _page(respx_mock, "/jobs", SMALL_LISTING)
    if kind == "web":
        source_id = await _insert_web(db_session, user_id, GEEKJOB)
    else:
        source_id = await _insert_telegram(db_session, user_id, "other_chan")
    lease = datetime.now(UTC).replace(tzinfo=None)
    _during_fetch(
        monkeypatch, _update_source(source_id, initial_attempt_started_at=lease)
    )

    resp = await _patch(client, token, source_id, body)

    assert resp.status_code == 409, resp.text
    assert resp.json() == {"detail": BUSY}
    source = await _source_row(db_session, source_id)
    assert source is not None and source.kind == kind
    assert source.revision == 0
    assert await _count(db_session, VacancySource) == 1


async def test_replace_labels_old_cards_with_the_name_set_during_the_fetch(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _page(respx_mock, "/jobs", SMALL_LISTING)
    old_id = await _insert_telegram(db_session, user_id, "other_chan")
    card_id = await _add_pending(db_session, user_id, old_id, "k1", state="new")
    _during_fetch(monkeypatch, _update_source(old_id, display_name="Renamed"))

    resp = await _patch(client, token, old_id, {"input": EXAMPLE_JOBS})

    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    label = await db_session.scalar(
        select(VacancyCardSource.label).where(VacancyCardSource.vacancy_id == card_id)
    )
    assert label == "Renamed"


async def test_replace_refused_when_the_source_was_edited_during_the_fetch(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _page(respx_mock, "/jobs", SMALL_LISTING)
    old_id = await _insert_telegram(db_session, user_id, "other_chan")
    _during_fetch(monkeypatch, _update_source(old_id, revision=1))

    resp = await _patch(client, token, old_id, {"input": EXAMPLE_JOBS})

    assert resp.status_code == 409, resp.text
    assert resp.json() == {"detail": BUSY}
    source = await _source_row(db_session, old_id)
    assert source is not None and source.kind == "telegram"
    assert await _count(db_session, VacancySource) == 1


# --- no network while a transaction is open (API side) ------------------------------


class _TrackingSessions:
    """The app's session factory, remembering every session it made."""

    def __init__(self) -> None:
        self.sessions: list[AsyncSession] = []

    def __call__(self) -> AsyncSession:
        session = _real_session_local()
        self.sessions.append(session)
        return session

    def open_transactions(self) -> int:
        return sum(1 for s in self.sessions if s.in_transaction())


@pytest.mark.parametrize(
    ("action", "kind", "body"),
    [
        ("preview", None, {"input": EXAMPLE_JOBS}),
        ("add", None, {"input": EXAMPLE_JOBS}),
        ("add", None, {"input": "@durov_jobs"}),
        ("edit", "web", {"job_link_contains": "/vacancy/"}),
        ("edit", "telegram", {"input": EXAMPLE_JOBS}),
        ("edit", "web", {"input": "@durov_jobs"}),
    ],
)
async def test_no_network_call_while_a_transaction_is_open(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    kind: str | None,
    body: dict,
) -> None:
    _page(respx_mock, "/jobs", SMALL_LISTING)
    _page(respx_mock, "/vacancies", SMALL_LISTING)
    tracking = _TrackingSessions()
    # The app's `get_db` override looks this name up on every request.
    monkeypatch.setattr(root_conftest, "TestSessionLocal", tracking)
    open_at_call: list[int] = []
    real_listing = vacancy_source_service.read_web_listing

    async def listing(*args: Any, **kwargs: Any) -> Any:
        open_at_call.append(tracking.open_transactions())
        return await real_listing(*args, **kwargs)

    async def name(*args: Any, **kwargs: Any) -> str:
        open_at_call.append(tracking.open_transactions())
        return "Durov jobs"

    monkeypatch.setattr(vacancy_source_service, "read_web_listing", listing)
    monkeypatch.setattr(vacancy_source_service, "_fetch_display_name", name)

    if action == "preview":
        resp = await client.post(PREVIEW_URL, json=body, headers=_auth(token))
    elif action == "add":
        resp = await client.post(URL, json=body, headers=_auth(token))
    else:
        source_id = (
            await _insert_web(db_session, user_id, GEEKJOB)
            if kind == "web"
            else await _insert_telegram(db_session, user_id, "other_chan")
        )
        resp = await _patch(client, token, source_id, body)

    assert resp.status_code in (200, 201), resp.text
    assert tracking.sessions, "the request used the tracked factory"
    assert open_at_call and open_at_call == [0] * len(open_at_call)
