"""PR #39 pre-merge findings through the API (M2, M3, M5, LOWs)."""

import asyncio
import hashlib
import json
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.discovery.fetchers import ashby
from app.models.vacancy import Vacancy
from app.models.vacancy_source import VacancySource
from app.services import vacancy_source_check, vacancy_source_service
from tests.test_vacancy_sources_followup_api import (  # noqa: F401 - autouse fixture
    _stub_network,
)
from tests.test_vacancy_web_sources_api import _add_pending


@pytest.fixture
def token(registered_user: dict) -> str:
    return registered_user["access_token"]


URL = "/api/v1/vacancy-sources"
PREVIEW_URL = f"{URL}/preview"
PUBLIC_IP = "93.184.216.34"
FIXTURES = Path(__file__).parent / "discovery_boards" / "fixtures"
GEEKJOB_REACT = json.loads((FIXTURES / "geekjob_react.json").read_text("utf-8"))
CANONICAL = "https://geekjob.ru/vacancies?qs=react"
BLOCKED = "This site blocks automated readers"
CANNOT_OPEN = "Could not open this page"
DUPLICATE = "Already in your sources"
ASHBY_API = "https://api.ashbyhq.com/posting-api/job-board/acme"

# Spellings the geekjob adapter turns into the very same JSON request.
SAME_SEARCH = [
    "https://www.geekjob.ru/vacancies?qs=react",
    "https://geekjob.ru/vacancies/2?qs=react",
    "https://geekjob.ru/vacancies/?qs=react",
    "https://geekjob.ru/vacancies?qs=react&or=1,2",
    "https://geekjob.ru/vacancies?qs=react&money=5",
    "https://geekjob.ru/vacancies?qs=react&f=1",
    "https://geekjob.ru/vacancies?qs=react&qs=vue",
    "https://geekjob.ru/vacancies?qs=react&page=3&sort=2",
    "https://GEEKJOB.RU./vacancies?qs=%20react%20",
    "geekjob.ru/vacancies?utm_source=tg&qs=react",
]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def user_id(registered_user: dict) -> str:
    return registered_user["user"]["id"]


@pytest.fixture
def geekjob_api(respx_mock: respx.MockRouter) -> respx.Route:
    return respx_mock.get(f"https://{PUBLIC_IP}/json/find/vacancy").respond(
        200, headers={"content-type": "application/json"}, json=GEEKJOB_REACT
    )


async def _count(db: AsyncSession, model: type) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


# --- M3: one hash per geekjob search --------------------------------------------------


@pytest.mark.parametrize("spelling", [CANONICAL, *SAME_SEARCH])
def test_every_spelling_has_the_canonical_url(spelling: str) -> None:
    parsed = vacancy_source_service.parse_input(spelling)

    assert parsed.url == CANONICAL


def test_canonical_url_keeps_every_filter_the_adapter_sends() -> None:
    parsed = vacancy_source_service.parse_input(
        "https://www.geekjob.ru/vacancies/3?na=1&rm=1&s=1&money=9&t=52,107&qs=a%20b"
        "&or=1&f=2&pt=1&ih=1&rl=1"
    )

    assert parsed.url == (
        "https://geekjob.ru/vacancies?qs=a+b&t=52%2C107&s=1&pt=1&ih=1&rm=1&rl=1&na=1"
    )


def test_other_sites_keep_their_normalized_url() -> None:
    parsed = vacancy_source_service.parse_input(
        "https://www.example.com/jobs?or=1&qs=x"
    )

    assert parsed.url == "https://www.example.com/jobs?or=1&qs=x"


async def test_add_stores_the_canonical_url(
    client: httpx.AsyncClient,
    token: str,
    geekjob_api: respx.Route,
    db_session: AsyncSession,
) -> None:
    resp = await client.post(
        URL,
        json={"input": "https://www.geekjob.ru/vacancies/2?qs=react&or=1"},
        headers=_auth(token),
    )

    assert resp.status_code == 201
    [source] = (await db_session.execute(select(VacancySource))).scalars().all()
    assert source.url == CANONICAL
    assert source.url_hash == _sha(CANONICAL)


@pytest.mark.parametrize("spelling", SAME_SEARCH)
async def test_second_add_of_the_same_search_is_a_duplicate(
    client: httpx.AsyncClient,
    token: str,
    geekjob_api: respx.Route,
    db_session: AsyncSession,
    spelling: str,
) -> None:
    first = await client.post(URL, json={"input": CANONICAL}, headers=_auth(token))
    assert first.status_code == 201
    calls = geekjob_api.call_count

    resp = await client.post(URL, json={"input": spelling}, headers=_auth(token))

    assert resp.status_code == 409
    assert resp.json() == {"detail": DUPLICATE}
    assert geekjob_api.call_count == calls  # refused before the network
    assert await _count(db_session, VacancySource) == 1


async def test_editing_only_ignored_params_is_a_no_op(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    geekjob_api: respx.Route,
    db_session: AsyncSession,
) -> None:
    created = await client.post(URL, json={"input": CANONICAL}, headers=_auth(token))
    source_id = created.json()["id"]
    await _add_pending(db_session, user_id, source_id, "p1")
    calls = geekjob_api.call_count

    resp = await client.patch(
        f"{URL}/{source_id}",
        json={"input": "https://www.geekjob.ru/vacancies/2?qs=react&or=1&money=7"},
        headers=_auth(token),
    )

    assert resp.status_code == 200
    assert geekjob_api.call_count == calls  # nothing re-read
    assert await _count(db_session, Vacancy) == 1  # pending row kept
    db_session.expire_all()
    source = await db_session.get(VacancySource, source_id)
    assert source is not None
    assert (source.url, source.revision) == (CANONICAL, 0)


async def test_legacy_stored_spelling_still_edits_as_a_no_op(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    geekjob_api: respx.Route,
    db_session: AsyncSession,
) -> None:
    # A source saved before canonical URLs: its own spelling and hash.
    legacy = "https://www.geekjob.ru/vacancies?qs=react&or=1"
    source = VacancySource(
        user_id=user_id,
        kind="web",
        handle="placeholder",
        url=legacy,
        url_hash=_sha(legacy),
        default_name="geekjob.ru",
        display_name="geekjob.ru",
    )
    db_session.add(source)
    await db_session.flush()
    source.handle = source.id
    await db_session.commit()
    source_id = source.id

    resp = await client.patch(
        f"{URL}/{source_id}", json={"input": CANONICAL}, headers=_auth(token)
    )

    assert resp.status_code == 200
    assert not geekjob_api.calls
    db_session.expire_all()
    row = await db_session.get(VacancySource, source_id)
    assert row is not None and row.url == legacy and row.revision == 0


# --- M2: a page of archived items through preview --------------------------------------


async def test_preview_pages_past_an_all_archived_page(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    archived = {"modify": "1", "archived": {"$date": 1}}

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        if page == 1:
            body = {
                "nextpage": 2,
                "data": [{"id": "old1", "position": "Old", "log": archived}],
            }
        else:
            body = {"nextpage": 0, "data": [{"id": "new1", "position": "React Dev"}]}
        return httpx.Response(
            200, headers={"content-type": "application/json"}, json=body
        )

    respx_mock.get(f"https://{PUBLIC_IP}/json/find/vacancy").mock(side_effect=handler)

    resp = await client.post(
        PREVIEW_URL, json={"input": CANONICAL}, headers=_auth(token)
    )

    # Preview reads page 1 only: no jobs there, so the usual 400.
    assert resp.status_code == 400

    saved = await client.post(URL, json={"input": CANONICAL}, headers=_auth(token))

    # Saving reads up to 5 pages and finds the job on page 2.
    assert saved.status_code == 201


# --- LOW: parser failure reads as "could not open" -----------------------------------


async def test_parser_failure_is_could_not_open(
    client: httpx.AsyncClient,
    token: str,
    geekjob_api: respx.Route,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.discovery.fetchers import site_listing

    def boom(*args: object) -> object:
        raise RuntimeError("parser bug")

    monkeypatch.setattr(site_listing, "_geekjob_jobs", boom)

    resp = await client.post(
        PREVIEW_URL, json={"input": CANONICAL}, headers=_auth(token)
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": CANNOT_OPEN}


# --- LOW: one blocked text, boards included ---------------------------------------------


def test_api_and_worker_share_the_blocked_text() -> None:
    from app.discovery.service import READ_ERROR_MESSAGES

    assert vacancy_source_check.SITE_BLOCKED_MESSAGE == BLOCKED
    assert READ_ERROR_MESSAGES["blocked"] == BLOCKED


async def test_blocked_board_api_shows_the_blocked_text(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(ASHBY_API).respond(403, headers={"cf-mitigated": "challenge"})

    resp = await client.post(
        URL, json={"input": "jobs.ashbyhq.com/acme"}, headers=_auth(token)
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": BLOCKED}


async def test_ashby_link_with_a_fragment_can_be_added(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(ASHBY_API).respond(200, json={"jobs": []})

    resp = await client.post(
        URL,
        json={"input": "https://jobs.ashbyhq.com/acme#openings"},
        headers=_auth(token),
    )

    assert resp.status_code == 201
    assert resp.json()["key"] == "ashby:acme"


# --- M5: one Ashby live check at a time -------------------------------------------------


async def test_ashby_live_checks_run_one_at_a_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    running = 0
    peak = 0

    async def fake_check(client: httpx.AsyncClient, org: str) -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        running -= 1

    monkeypatch.setattr(ashby, "check_board", fake_check)

    names = await asyncio.gather(
        *(vacancy_source_check.check_ashby_board(f"org{i}") for i in range(3))
    )

    assert names == ["Org0", "Org1", "Org2"]
    assert peak == 1
