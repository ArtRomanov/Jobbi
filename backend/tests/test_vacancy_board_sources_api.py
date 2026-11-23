"""POST /vacancy-sources for Greenhouse, Lever and Teamtailor boards (respx)."""

import asyncio
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vacancy_source import VacancySource
from app.services import vacancy_source_check

URL = "/api/v1/vacancy-sources"
GH_BOARD_URL = "https://boards-api.greenhouse.io/v1/boards/acme"
LEVER_URL = "https://api.lever.co/v0/postings/acme-labs"
LEVER_EU_URL = "https://api.eu.lever.co/v0/postings/acme-labs"
UNREADABLE = "Could not read this job board"
DUPLICATE = "Already in your sources"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def token(registered_user: dict) -> str:
    return registered_user["access_token"]


@pytest.fixture
def gh_route(respx_mock: respx.MockRouter) -> respx.Route:
    return respx_mock.get(GH_BOARD_URL).mock(
        return_value=httpx.Response(200, json={"name": "  Acme Corp ", "content": ""})
    )


@pytest.fixture
def lever_route(respx_mock: respx.MockRouter) -> respx.Route:
    return respx_mock.get(LEVER_URL).mock(
        return_value=httpx.Response(200, json=[{"id": "x", "text": "Dev"}])
    )


@pytest.fixture
def lever_eu_route(respx_mock: respx.MockRouter) -> respx.Route:
    return respx_mock.get(LEVER_EU_URL).mock(return_value=httpx.Response(200, json=[]))


async def _sources(db: AsyncSession) -> list[VacancySource]:
    return list((await db.execute(select(VacancySource))).scalars().all())


# --- Greenhouse --------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "https://boards.greenhouse.io/acme",
        "https://job-boards.eu.greenhouse.io/Acme/jobs/123?gh_jid=123",
    ],
)
async def test_add_greenhouse_board_uses_board_name(
    client: httpx.AsyncClient,
    token: str,
    gh_route: respx.Route,
    db_session: AsyncSession,
    raw: str,
) -> None:
    resp = await client.post(URL, json={"input": raw}, headers=_auth(token))

    assert resp.status_code == 201
    data = resp.json()
    assert data["kind"] == "greenhouse"
    assert data["key"] == "greenhouse:acme"
    assert data["display_name"] == "Acme Corp"
    assert data["scanning"] is True
    # EU links are served by the standard API host; one request, no redirects.
    assert gh_route.call_count == 1
    request = gh_route.calls.last.request
    assert str(request.url) == GH_BOARD_URL
    assert request.headers["User-Agent"] == "Jobbi/1.0"
    [source] = await _sources(db_session)
    assert (source.kind, source.handle) == ("greenhouse", "acme")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404, json={"status": 404}),
        httpx.Response(500),
        httpx.Response(429),
        httpx.Response(301, headers={"Location": "https://evil.example/"}),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"no_name": True}),
        httpx.ConnectError("boom"),
        httpx.ReadTimeout("slow"),
    ],
    ids=[
        "404",
        "500",
        "429",
        "redirect",
        "bad-json",
        "no-name",
        "connect-error",
        "timeout",
    ],
)
async def test_unreadable_greenhouse_board(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
    response: httpx.Response | Exception,
) -> None:
    respx_mock.get(GH_BOARD_URL).mock(side_effect=[response])

    resp = await client.post(
        URL, json={"input": "boards.greenhouse.io/acme"}, headers=_auth(token)
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": UNREADABLE}
    assert await _sources(db_session) == []


async def test_board_check_has_a_total_time_budget(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    monkeypatch.setattr(vacancy_source_check, "CHECK_TIMEOUT_SECONDS", 0.05)

    async def _slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json={"name": "Acme"})

    respx_mock.get(GH_BOARD_URL).mock(side_effect=_slow)

    resp = await client.post(
        URL, json={"input": "boards.greenhouse.io/acme"}, headers=_auth(token)
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": UNREADABLE}
    assert await _sources(db_session) == []


@pytest.mark.parametrize(
    "second",
    [
        "boards.greenhouse.io/acme",
        "https://job-boards.greenhouse.io/ACME/",
        "https://boards.eu.greenhouse.io/acme",
        "https://job-boards.eu.greenhouse.io/acme/jobs/42?gh_jid=42",
    ],
)
async def test_greenhouse_duplicate_across_link_forms(
    client: httpx.AsyncClient,
    token: str,
    gh_route: respx.Route,
    db_session: AsyncSession,
    second: str,
) -> None:
    first = await client.post(
        URL, json={"input": "https://boards.greenhouse.io/acme"}, headers=_auth(token)
    )
    assert first.status_code == 201

    resp = await client.post(URL, json={"input": second}, headers=_auth(token))

    assert resp.status_code == 409
    assert resp.json() == {"detail": DUPLICATE}
    assert gh_route.call_count == 1  # rejected before the network
    assert len(await _sources(db_session)) == 1


# --- Lever -------------------------------------------------------------------------


async def test_add_lever_board_derives_name_from_slug(
    client: httpx.AsyncClient,
    token: str,
    lever_route: respx.Route,
    db_session: AsyncSession,
) -> None:
    resp = await client.post(
        URL,
        json={
            "input": "https://jobs.lever.co/Acme-Labs/065f4538-7347-4207-909f-4ea68f63b4af"
        },
        headers=_auth(token),
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["kind"] == "lever"
    assert data["key"] == "lever:acme-labs"
    assert data["display_name"] == "Acme Labs"
    # One small request (limit=1) is enough to prove the board exists.
    assert lever_route.call_count == 1
    params = lever_route.calls.last.request.url.params
    assert params["limit"] == "1"
    assert params["mode"] == "json"
    [source] = await _sources(db_session)
    assert (source.kind, source.handle) == ("lever", "acme-labs")


async def test_add_lever_eu_board_uses_eu_host(
    client: httpx.AsyncClient,
    token: str,
    lever_eu_route: respx.Route,
) -> None:
    resp = await client.post(
        URL, json={"input": "jobs.eu.lever.co/acme-labs"}, headers=_auth(token)
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["kind"] == "lever_eu"
    assert data["key"] == "lever_eu:acme-labs"
    assert data["display_name"] == "Acme Labs"
    assert lever_eu_route.call_count == 1


async def test_lever_404_is_unreadable_and_other_region_not_tried(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
) -> None:
    us = respx_mock.get(LEVER_URL).mock(return_value=httpx.Response(404))
    eu = respx_mock.get(LEVER_EU_URL).mock(return_value=httpx.Response(200, json=[]))

    resp = await client.post(
        URL, json={"input": "jobs.lever.co/acme-labs"}, headers=_auth(token)
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": UNREADABLE}
    assert us.call_count == 1
    assert eu.call_count == 0
    assert await _sources(db_session) == []


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503),
        httpx.Response(200, json={"ok": False}),
        httpx.ConnectTimeout("slow"),
    ],
    ids=["503", "not-a-list", "timeout"],
)
async def test_unreadable_lever_board(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
    response: httpx.Response | Exception,
) -> None:
    respx_mock.get(LEVER_EU_URL).mock(side_effect=[response])

    resp = await client.post(
        URL, json={"input": "jobs.eu.lever.co/acme-labs"}, headers=_auth(token)
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": UNREADABLE}
    assert await _sources(db_session) == []


@pytest.mark.parametrize(
    "second",
    [
        "jobs.lever.co/acme-labs",
        "https://jobs.lever.co/ACME-LABS/",
        "https://jobs.lever.co/acme-labs/065f4538-7347-4207-909f-4ea68f63b4af/apply",
    ],
)
async def test_lever_duplicate_across_link_forms(
    client: httpx.AsyncClient,
    token: str,
    lever_route: respx.Route,
    db_session: AsyncSession,
    second: str,
) -> None:
    first = await client.post(
        URL, json={"input": "https://jobs.lever.co/acme-labs"}, headers=_auth(token)
    )
    assert first.status_code == 201

    resp = await client.post(URL, json={"input": second}, headers=_auth(token))

    assert resp.status_code == 409
    assert resp.json() == {"detail": DUPLICATE}
    assert lever_route.call_count == 1
    assert len(await _sources(db_session)) == 1


async def test_same_slug_in_us_and_eu_are_different_boards(
    client: httpx.AsyncClient,
    token: str,
    lever_route: respx.Route,
    lever_eu_route: respx.Route,
    db_session: AsyncSession,
) -> None:
    us = await client.post(
        URL, json={"input": "jobs.lever.co/acme-labs"}, headers=_auth(token)
    )
    eu = await client.post(
        URL, json={"input": "jobs.eu.lever.co/acme-labs"}, headers=_auth(token)
    )

    assert (us.status_code, eu.status_code) == (201, 201)
    assert {s.kind for s in await _sources(db_session)} == {"lever", "lever_eu"}


async def test_boards_listed_with_their_names(
    client: httpx.AsyncClient,
    token: str,
    lever_route: respx.Route,
    gh_route: respx.Route,
) -> None:
    gh = await client.post(
        URL, json={"input": "boards.greenhouse.io/acme"}, headers=_auth(token)
    )
    lv = await client.post(
        URL, json={"input": "jobs.lever.co/acme-labs"}, headers=_auth(token)
    )

    assert (gh.status_code, lv.status_code) == (201, 201)
    listed = (await client.get(URL, headers=_auth(token))).json()["sources"]
    # Both may share a created_at second, so compare without order.
    assert {(s["kind"], s["display_name"]) for s in listed} == {
        ("greenhouse", "Acme Corp"),
        ("lever", "Acme Labs"),
    }


# --- Teamtailor --------------------------------------------------------------------

TT_FEED_URL = "https://approvalmax.teamtailor.com/jobs.rss"
TT_FEED = (
    Path(__file__).parent / "discovery_boards/fixtures/teamtailor_approvalmax.rss"
).read_bytes()


@pytest.fixture
def tt_route(respx_mock: respx.MockRouter) -> respx.Route:
    return respx_mock.get(TT_FEED_URL).mock(
        return_value=httpx.Response(200, content=TT_FEED)
    )


@pytest.mark.parametrize(
    "raw",
    [
        "approvalmax.teamtailor.com",
        "https://ApprovalMax.teamtailor.com/jobs/8683780-director-of-product",
    ],
)
async def test_add_teamtailor_board_uses_channel_title(
    client: httpx.AsyncClient,
    token: str,
    tt_route: respx.Route,
    db_session: AsyncSession,
    raw: str,
) -> None:
    resp = await client.post(URL, json={"input": raw}, headers=_auth(token))

    assert resp.status_code == 201
    data = resp.json()
    assert data["kind"] == "teamtailor"
    assert data["key"] == "teamtailor:approvalmax"
    assert data["display_name"] == "ApprovalMax"
    assert data["scanning"] is True
    # Only the fixed feed URL is requested, whatever path the user pasted.
    assert tt_route.call_count == 1
    request = tt_route.calls.last.request
    assert str(request.url) == TT_FEED_URL
    assert request.headers["User-Agent"] == "Jobbi/1.0"
    [source] = await _sources(db_session)
    assert (source.kind, source.handle) == ("teamtailor", "approvalmax")
    assert source.initial_scan_completed_at is None  # the worker does the first scan


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404),
        httpx.Response(500),
        httpx.Response(302, headers={"Location": "https://evil.example/"}),
        httpx.Response(200, content=b"<html>not a feed</html>"),
        httpx.Response(
            200,
            content=b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">]>'
            b"<rss><channel><title>&a;</title></channel></rss>",
        ),
        httpx.Response(200, content=b"<rss><channel><title></title></channel></rss>"),
        httpx.ConnectError("boom"),
    ],
    ids=["404", "500", "redirect", "html", "doctype", "no-title", "connect-error"],
)
async def test_unreadable_teamtailor_board(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
    response: httpx.Response | Exception,
) -> None:
    respx_mock.get(TT_FEED_URL).mock(side_effect=[response])

    resp = await client.post(
        URL, json={"input": "approvalmax.teamtailor.com"}, headers=_auth(token)
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": UNREADABLE}
    assert await _sources(db_session) == []


@pytest.mark.parametrize(
    "second",
    [
        "approvalmax.teamtailor.com",
        "https://APPROVALMAX.teamtailor.com/",
        "https://approvalmax.teamtailor.com/jobs/8653872-revenue-operations-specialist",
    ],
)
async def test_teamtailor_duplicate_across_link_forms(
    client: httpx.AsyncClient,
    token: str,
    tt_route: respx.Route,
    db_session: AsyncSession,
    second: str,
) -> None:
    first = await client.post(
        URL,
        json={"input": "https://approvalmax.teamtailor.com/jobs"},
        headers=_auth(token),
    )
    assert first.status_code == 201

    resp = await client.post(URL, json={"input": second}, headers=_auth(token))

    assert resp.status_code == 409
    assert resp.json() == {"detail": DUPLICATE}
    assert tt_route.call_count == 1  # rejected before the network
    assert len(await _sources(db_session)) == 1


@pytest.mark.parametrize(
    "raw",
    [
        "approvalmax.teamtailor.com.evil.com",
        "https://evil.com/approvalmax.teamtailor.com",
        "https://a@approvalmax.teamtailor.com/jobs",
        "https://approvalmax.teamtailor.com:8443/jobs",
        "clever.com/careers",
    ],
)
async def test_teamtailor_lookalikes_make_no_network_call(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
    raw: str,
) -> None:
    resp = await client.post(URL, json={"input": raw}, headers=_auth(token))

    assert resp.status_code == 400
    assert not respx_mock.calls
    assert await _sources(db_session) == []
