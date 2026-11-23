"""Spec 010 §2.6 through the API: Ashby boards, geekjob search links, blocked sites.

Board requests go to fixed hosts (respx). Web pages go through `safe_http`
with a stub resolver (no real DNS), so respx sees the pinned-IP requests.
"""

import json
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.discovery import web_scan
from app.discovery.fetchers import safe_http
from app.models.vacancy_seen_key import VacancySeenKey
from app.models.vacancy_source import VacancySource

URL = "/api/v1/vacancy-sources"
PREVIEW_URL = f"{URL}/preview"
PUBLIC_IP = "93.184.216.34"
FIXTURES = Path(__file__).parent / "discovery_boards" / "fixtures"
ASHBY_API = "https://api.ashbyhq.com/posting-api/job-board/manychat"
ASHBY_BOARD = json.loads((FIXTURES / "ashby_manychat.json").read_text("utf-8"))
GEEKJOB_REACT = json.loads((FIXTURES / "geekjob_react.json").read_text("utf-8"))
GEEKJOB_SEARCH = "https://geekjob.ru/vacancies?qs=react"
UNREADABLE = "Could not read this job board"
BOARD_INVALID = "Not a Greenhouse, Lever, Teamtailor or Ashby job board link"
BLOCKED = "This site blocks automated readers — try its job board link instead"
DUPLICATE = "Already in your sources"
CF_HEADERS = {
    "content-type": "text/html; charset=UTF-8",
    "cf-mitigated": "challenge",
    "server": "cloudflare",
}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _stub_network(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _resolve(host: str, port: int) -> list[str]:
        return [PUBLIC_IP]

    monkeypatch.setattr(safe_http, "system_resolver", _resolve)
    monkeypatch.setattr(web_scan, "PAGE_PAUSE_SECONDS", 0.0)


@pytest.fixture
def token(registered_user: dict) -> str:
    return registered_user["access_token"]


async def _sources(db: AsyncSession) -> list[VacancySource]:
    return list((await db.execute(select(VacancySource))).scalars().all())


# --- Ashby ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "jobs.ashbyhq.com/manychat",
        "https://jobs.ashbyhq.com/ManyChat/72eaca21-1d04-4e08-ac70-c987519dda1f",
    ],
)
async def test_add_ashby_board(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
    raw: str,
) -> None:
    route = respx_mock.get(ASHBY_API).respond(200, json=ASHBY_BOARD)

    resp = await client.post(URL, json={"input": raw}, headers=_auth(token))

    assert resp.status_code == 201
    data = resp.json()
    assert data["kind"] == "ashby"
    assert data["key"] == "ashby:manychat"
    assert data["display_name"] == "Manychat"
    assert data["scanning"] is True
    # Only the fixed API URL is requested, whatever path the user pasted.
    assert route.call_count == 1
    request = route.calls.last.request
    assert str(request.url) == f"{ASHBY_API}?includeCompensation=false"
    [source] = await _sources(db_session)
    assert (source.kind, source.handle) == ("ashby", "manychat")
    assert source.initial_scan_completed_at is None  # the worker does the first scan


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404, text="Not Found"),
        httpx.Response(500),
        httpx.Response(302, headers={"Location": "https://evil.example/"}),
        httpx.Response(200, content=b"<html>no</html>"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"jobs": "x"}),
        httpx.ConnectError("boom"),
        httpx.Response(200, content=b"[" * 100_000 + b"]" * 100_000),
    ],
    ids=[
        "404",
        "500",
        "redirect",
        "html",
        "list",
        "bad-jobs",
        "connect-error",
        "deep-nesting",
    ],
)
async def test_unreadable_ashby_board(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
    response: httpx.Response | Exception,
) -> None:
    respx_mock.get(ASHBY_API).mock(side_effect=[response])

    resp = await client.post(
        URL, json={"input": "jobs.ashbyhq.com/manychat"}, headers=_auth(token)
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": UNREADABLE}
    assert await _sources(db_session) == []


async def test_ashby_duplicate_across_link_forms(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.get(ASHBY_API).respond(200, json=ASHBY_BOARD)
    first = await client.post(
        URL, json={"input": "jobs.ashbyhq.com/manychat"}, headers=_auth(token)
    )
    assert first.status_code == 201

    resp = await client.post(
        URL,
        json={"input": "https://JOBS.ashbyhq.com/Manychat/?utm_source=x"},
        headers=_auth(token),
    )

    assert resp.status_code == 409
    assert resp.json() == {"detail": DUPLICATE}
    assert route.call_count == 1  # rejected before the network


@pytest.mark.parametrize(
    "raw",
    [
        "https://jobs.ashbyhq.com/",
        "https://jobs.ashbyhq.com/a..b",
        "https://a@jobs.ashbyhq.com/manychat",
        "https://jobs.ashbyhq.com:8443/manychat",
        "https://www.ashbyhq.com/",
    ],
)
async def test_bad_ashby_links_get_the_board_text_without_network(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter, raw: str
) -> None:
    resp = await client.post(URL, json={"input": raw}, headers=_auth(token))

    assert resp.status_code == 400
    assert resp.json() == {"detail": BOARD_INVALID}
    assert not respx_mock.calls


async def test_preview_of_an_ashby_link_is_kind_only(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    resp = await client.post(
        PREVIEW_URL, json={"input": "jobs.ashbyhq.com/manychat"}, headers=_auth(token)
    )

    assert resp.status_code == 200
    assert resp.json()["kind"] == "ashby"
    assert not respx_mock.calls


async def test_preview_hints_an_embedded_ashby_board(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"https://{PUBLIC_IP}/careers").respond(
        200,
        headers={"content-type": "text/html"},
        text='<html><body><div id="ashby_embed"></div>'
        '<script src="https://jobs.ashbyhq.com/manychat/embed?version=2"></script>'
        "</body></html>",
    )

    resp = await client.post(
        PREVIEW_URL, json={"input": "https://example.com/careers"}, headers=_auth(token)
    )

    assert resp.status_code == 200
    assert resp.json()["ats_hint"] == {
        "kind": "ashby",
        "input": "https://jobs.ashbyhq.com/manychat",
        "label": "Ashby",
    }
    assert len(respx_mock.calls) == 1  # the board itself is not fetched


# --- blocked sites ----------------------------------------------------------------


@pytest.fixture
def blocked_page(respx_mock: respx.MockRouter) -> respx.Route:
    # The live answer of careers.manychat.com/positions (Cloudflare challenge).
    return respx_mock.get(f"https://{PUBLIC_IP}/positions").respond(
        403, headers=CF_HEADERS, text="<title>Just a moment...</title>"
    )


async def test_preview_of_a_blocked_site(
    client: httpx.AsyncClient, token: str, blocked_page: respx.Route
) -> None:
    resp = await client.post(
        PREVIEW_URL,
        json={"input": "https://careers.manychat.com/positions"},
        headers=_auth(token),
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": BLOCKED}


async def test_save_of_a_blocked_site_saves_nothing(
    client: httpx.AsyncClient,
    token: str,
    blocked_page: respx.Route,
    db_session: AsyncSession,
) -> None:
    resp = await client.post(
        URL,
        json={"input": "https://careers.manychat.com/positions"},
        headers=_auth(token),
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": BLOCKED}
    assert await _sources(db_session) == []


async def test_edit_to_a_blocked_site_is_400_like_add(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    blocked_page: respx.Route,
    db_session: AsyncSession,
) -> None:
    respx_mock.get(ASHBY_API).respond(200, json=ASHBY_BOARD)
    created = await client.post(
        URL, json={"input": "jobs.ashbyhq.com/manychat"}, headers=_auth(token)
    )
    source_id = created.json()["id"]

    resp = await client.patch(
        f"{URL}/{source_id}",
        json={"input": "https://careers.manychat.com/positions"},
        headers=_auth(token),
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": BLOCKED}
    [source] = await _sources(db_session)
    assert (source.kind, source.handle) == ("ashby", "manychat")


# --- geekjob search links -----------------------------------------------------------


@pytest.fixture
def geekjob_api(respx_mock: respx.MockRouter) -> respx.Route:
    return respx_mock.get(f"https://{PUBLIC_IP}/json/find/vacancy").respond(
        200, headers={"content-type": "application/json"}, json=GEEKJOB_REACT
    )


async def test_preview_of_a_geekjob_search_shows_its_titles(
    client: httpx.AsyncClient, token: str, geekjob_api: respx.Route
) -> None:
    resp = await client.post(
        PREVIEW_URL, json={"input": GEEKJOB_SEARCH}, headers=_auth(token)
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "kind": "web",
        "default_name": "geekjob.ru",
        "found_count": 6,  # 8 items: one repeated, one archived
        "titles": [
            "Product Engineer",
            "Senior Fullstack Developer (Laravel + React) / Technical Lead",
            GEEKJOB_REACT["data"][3]["position"],
            "Product Engineer",
            "Junior QA Engineer",
        ],
        "ats_hint": None,
    }
    assert geekjob_api.call_count == 1
    request = geekjob_api.calls.last.request
    assert request.headers["host"] == "geekjob.ru"
    assert request.url.params["qs"] == "react"
    assert request.url.params["sort"] == "1"
    assert request.url.params["page"] == "1"


async def test_save_of_a_geekjob_search_records_its_jobs_as_seen(
    client: httpx.AsyncClient,
    token: str,
    geekjob_api: respx.Route,
    db_session: AsyncSession,
) -> None:
    resp = await client.post(URL, json={"input": GEEKJOB_SEARCH}, headers=_auth(token))

    assert resp.status_code == 201
    source_id = resp.json()["id"]
    keys = set(
        (await db_session.execute(select(VacancySeenKey.external_key))).scalars()
    )
    assert len(keys) == 6
    assert (
        web_scan.web_seen_key(
            source_id, "https://geekjob.ru/vacancy/6b01b96bc859285a74045e0c"
        )
        in keys
    )
    # One page: the answer's nextpage is 0.
    assert geekjob_api.call_count == 1


async def test_blocked_geekjob_endpoint_is_the_blocked_text(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"https://{PUBLIC_IP}/json/find/vacancy").respond(
        403, headers=CF_HEADERS, text=""
    )

    resp = await client.post(
        PREVIEW_URL, json={"input": GEEKJOB_SEARCH}, headers=_auth(token)
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": BLOCKED}
