import asyncio
import re
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vacancy_search_settings import VacancySearchSettings
from app.models.vacancy_source import VacancySource
from app.services import vacancy_source_check, vacancy_source_service
from app.services.vacancy_source_parsing import INVALID_INPUT_MESSAGE
from tests.conftest import TestSessionLocal

URL = "/api/v1/vacancy-sources"
CHANNEL_URL = "https://t.me/s/durov_jobs"
NOT_PUBLIC = "This channel is not public or does not exist"
UNREACHABLE = "Could not reach Telegram. Please try again."
UTC_SUFFIX = re.compile(r"(Z|\+00:00)$")

CHANNEL_PAGE = """<!DOCTYPE html><html><body>
<div class="tgme_channel_info">
  <div class="tgme_channel_info_header">
    <div class="tgme_channel_info_header_title"><span dir="auto">Durov&#39;s
      Jobs</span></div>
    <div class="tgme_channel_info_header_username"><a>@durov_jobs</a></div>
  </div>
</div>
<div class="tgme_widget_message_wrap"><div class="tgme_widget_message"
  data-post="durov_jobs/1"></div></div>
</body></html>"""

MESSAGES_ONLY_PAGE = """<html><body>
<div class="tgme_widget_message_wrap"><div data-post="durov_jobs/1"></div></div>
</body></html>"""

NOT_A_CHANNEL_PAGE = "<html><body><div class='tgme_page'>Hello</div></body></html>"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture
def token(registered_user: dict) -> str:
    return registered_user["access_token"]


@pytest.fixture
def user_id(registered_user: dict) -> str:
    return registered_user["user"]["id"]


@pytest.fixture
def channel_route(respx_mock: respx.MockRouter) -> respx.Route:
    """A public channel page at the fixed preview URL."""
    return respx_mock.get(CHANNEL_URL).mock(
        return_value=httpx.Response(200, text=CHANNEL_PAGE)
    )


async def _insert_source(
    db: AsyncSession, user_id: str, handle: str, **overrides: object
) -> VacancySource:
    source = VacancySource(
        user_id=user_id,
        kind="telegram",
        handle=handle,
        display_name=f"@{handle}",
        **overrides,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


async def _count_sources(db: AsyncSession) -> int:
    result = await db.execute(select(VacancySource))
    return len(result.scalars().all())


# ---------------------------------------------------------------------------
# GET /vacancy-sources
# ---------------------------------------------------------------------------


async def test_list_empty_with_defaults(client: httpx.AsyncClient, token: str) -> None:
    resp = await client.get(URL, headers=_auth(token))

    assert resp.status_code == 200
    assert resp.json() == {
        "sources": [],
        "removed_sources": [],
        "settings": {"description": None, "exclude": []},
        "status": {"ai_unavailable": False, "limit_reached": False, "waiting_count": 0},
    }


async def test_list_reads_saved_settings(
    client: httpx.AsyncClient, token: str, user_id: str, db_session: AsyncSession
) -> None:
    db_session.add(
        VacancySearchSettings(
            user_id=user_id,
            description="Senior frontend, remote",
            exclude_terms=["java", "office only"],
        )
    )
    await db_session.commit()

    resp = await client.get(URL, headers=_auth(token))

    assert resp.json()["settings"] == {
        "description": "Senior frontend, remote",
        "exclude": ["java", "office only"],
    }


async def test_list_reports_scanning_and_unavailable(
    client: httpx.AsyncClient, token: str, user_id: str, db_session: AsyncSession
) -> None:
    now = _now_naive()
    await _insert_source(db_session, user_id, "scanning_one")
    await _insert_source(
        db_session,
        user_id,
        "healthy_one",
        initial_scan_completed_at=now,
        last_checked_at=now,
    )
    await _insert_source(
        db_session,
        user_id,
        "failing_recently",
        initial_scan_completed_at=now,
        failing_since=now - timedelta(hours=1),
        last_error="Could not read",
    )
    await _insert_source(
        db_session,
        user_id,
        "failing_long",
        initial_scan_completed_at=now,
        failing_since=now - timedelta(hours=25),
        last_error="Could not read",
    )

    resp = await client.get(URL, headers=_auth(token))

    by_name = {s["display_name"]: s for s in resp.json()["sources"]}
    assert by_name["@scanning_one"]["scanning"] is True
    assert by_name["@scanning_one"]["last_checked_at"] is None
    assert by_name["@healthy_one"]["scanning"] is False
    assert by_name["@healthy_one"]["unavailable"] is False
    assert UTC_SUFFIX.search(by_name["@healthy_one"]["last_checked_at"])
    assert by_name["@failing_recently"]["unavailable"] is False
    assert by_name["@failing_long"]["unavailable"] is True
    assert by_name["@failing_long"]["last_error"] == "Could not read"


async def test_list_requires_auth(client: httpx.AsyncClient) -> None:
    resp = await client.get(URL)
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# POST /vacancy-sources — happy path
# ---------------------------------------------------------------------------


async def test_add_public_channel(
    client: httpx.AsyncClient, token: str, channel_route: respx.Route
) -> None:
    resp = await client.post(URL, json={"input": "@Durov_Jobs"}, headers=_auth(token))

    assert resp.status_code == 201
    data = resp.json()
    assert set(data) == {
        "id",
        "key",
        "kind",
        "display_name",
        "last_checked_at",
        "scanning",
        "unavailable",
        "last_error",
    }
    assert data["kind"] == "telegram"
    assert data["key"] == "telegram:durov_jobs"
    assert data["display_name"] == "Durov's Jobs"
    assert data["scanning"] is True
    assert data["unavailable"] is False
    assert data["last_checked_at"] is None
    assert data["last_error"] is None

    listed = (await client.get(URL, headers=_auth(token))).json()["sources"]
    assert listed == [data]


async def test_live_check_uses_fixed_host_without_redirects(
    client: httpx.AsyncClient, token: str, channel_route: respx.Route
) -> None:
    resp = await client.post(
        URL, json={"input": "https://t.me/s/DUROV_JOBS/42"}, headers=_auth(token)
    )

    assert resp.status_code == 201
    assert channel_route.call_count == 1
    request = channel_route.calls.last.request
    assert str(request.url) == CHANNEL_URL
    assert request.headers["User-Agent"] == "Jobbi/1.0"


async def test_add_stores_lowercased_handle(
    client: httpx.AsyncClient,
    token: str,
    channel_route: respx.Route,
    db_session: AsyncSession,
) -> None:
    await client.post(URL, json={"input": "t.me/Durov_Jobs"}, headers=_auth(token))

    source = (await db_session.execute(select(VacancySource))).scalar_one()
    assert source.handle == "durov_jobs"


async def test_display_name_falls_back_to_handle(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(CHANNEL_URL).mock(
        return_value=httpx.Response(200, text=MESSAGES_ONLY_PAGE)
    )

    resp = await client.post(URL, json={"input": "@durov_jobs"}, headers=_auth(token))

    assert resp.status_code == 201
    assert resp.json()["display_name"] == "@durov_jobs"


async def test_oversized_page_is_capped(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vacancy_source_check, "MAX_RESPONSE_BYTES", 2_000)
    respx_mock.get(CHANNEL_URL).mock(
        return_value=httpx.Response(200, text=CHANNEL_PAGE + "x" * 500_000)
    )

    resp = await client.post(URL, json={"input": "@durov_jobs"}, headers=_auth(token))

    assert resp.status_code == 201
    assert resp.json()["display_name"] == "Durov's Jobs"


# ---------------------------------------------------------------------------
# POST /vacancy-sources — errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(302, headers={"Location": "https://t.me/durov_jobs"}),
        httpx.Response(404),
        httpx.Response(200, text=NOT_A_CHANNEL_PAGE),
    ],
    ids=["redirect", "not-found", "no-channel-info"],
)
async def test_not_public_channel(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
    response: httpx.Response,
) -> None:
    route = respx_mock.get(CHANNEL_URL).mock(return_value=response)

    resp = await client.post(URL, json={"input": "@durov_jobs"}, headers=_auth(token))

    assert resp.status_code == 400
    assert resp.json() == {"detail": NOT_PUBLIC}
    assert route.call_count == 1  # the redirect was not followed
    assert await _count_sources(db_session) == 0


@pytest.mark.parametrize(
    "side_effect",
    [
        httpx.ConnectTimeout("timed out"),
        httpx.ReadTimeout("timed out"),
        httpx.ConnectError("no route"),
        httpx.Response(503),
        httpx.Response(429),
    ],
    ids=["connect-timeout", "read-timeout", "connect-error", "503", "429"],
)
async def test_telegram_unreachable(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
    side_effect: Exception | httpx.Response,
) -> None:
    respx_mock.get(CHANNEL_URL).mock(side_effect=[side_effect])

    resp = await client.post(URL, json={"input": "@durov_jobs"}, headers=_auth(token))

    assert resp.status_code == 400
    assert resp.json() == {"detail": UNREACHABLE}
    assert await _count_sources(db_session) == 0


async def test_total_timeout_budget(
    client: httpx.AsyncClient,
    token: str,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vacancy_source_check, "CHECK_TIMEOUT_SECONDS", 0.05)

    async def _slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, text=CHANNEL_PAGE)

    respx_mock.get(CHANNEL_URL).mock(side_effect=_slow)

    resp = await client.post(URL, json={"input": "@durov_jobs"}, headers=_auth(token))

    assert resp.status_code == 400
    assert resp.json() == {"detail": UNREACHABLE}


@pytest.mark.parametrize(
    "raw",
    [
        "https://evil.com/durov_jobs",
        "t.me.evil.com/durov_jobs",
        "javascript:alert(1)",
        "@abc",
        "https://boards.greenhouse.io/acme",
    ],
)
async def test_invalid_input_makes_no_network_call(
    client: httpx.AsyncClient, token: str, respx_mock: respx.MockRouter, raw: str
) -> None:
    resp = await client.post(URL, json={"input": raw}, headers=_auth(token))

    assert resp.status_code == 400
    assert resp.json() == {"detail": INVALID_INPUT_MESSAGE}
    assert not respx_mock.calls


async def test_missing_input_is_validation_error(
    client: httpx.AsyncClient, token: str
) -> None:
    resp = await client.post(URL, json={}, headers=_auth(token))
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "second_input",
    ["@DUROV_JOBS", "t.me/durov_jobs", "https://t.me/s/Durov_Jobs/7", "durov_jobs"],
)
async def test_duplicate_in_another_form(
    client: httpx.AsyncClient,
    token: str,
    channel_route: respx.Route,
    db_session: AsyncSession,
    second_input: str,
) -> None:
    first = await client.post(URL, json={"input": "@Durov_Jobs"}, headers=_auth(token))
    assert first.status_code == 201

    resp = await client.post(URL, json={"input": second_input}, headers=_auth(token))

    assert resp.status_code == 409
    assert resp.json() == {"detail": "Already in your sources"}
    assert channel_route.call_count == 1  # duplicate rejected before the network
    assert await _count_sources(db_session) == 1


async def test_duplicate_added_during_live_check(
    client: httpx.AsyncClient, token: str, user_id: str, respx_mock: respx.MockRouter
) -> None:
    """A concurrent request saves the same channel while we wait on Telegram."""

    async def _race(request: httpx.Request) -> httpx.Response:
        async with TestSessionLocal() as other:
            await _insert_source(other, user_id, "durov_jobs")
        return httpx.Response(200, text=CHANNEL_PAGE)

    respx_mock.get(CHANNEL_URL).mock(side_effect=_race)

    resp = await client.post(URL, json={"input": "@durov_jobs"}, headers=_auth(token))

    assert resp.status_code == 409
    assert resp.json() == {"detail": "Already in your sources"}


async def test_unique_constraint_maps_to_conflict(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    channel_route: respx.Route,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If both checks miss a duplicate, the DB constraint still answers 409."""
    await _insert_source(db_session, user_id, "durov_jobs")

    async def _never_exists(*_: object) -> bool:
        return False

    monkeypatch.setattr(vacancy_source_service, "_source_exists", _never_exists)

    resp = await client.post(URL, json={"input": "@durov_jobs"}, headers=_auth(token))

    assert resp.status_code == 409
    assert resp.json() == {"detail": "Already in your sources"}
    assert await _count_sources(db_session) == 1


async def test_limit_of_30_sources(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    respx_mock: respx.MockRouter,
    db_session: AsyncSession,
) -> None:
    for i in range(30):
        await _insert_source(db_session, user_id, f"channel_{i:02d}")

    resp = await client.post(URL, json={"input": "@durov_jobs"}, headers=_auth(token))

    assert resp.status_code == 400
    assert resp.json() == {"detail": "You can watch up to 30 sources"}
    assert not respx_mock.calls  # limit checked before the network
    assert await _count_sources(db_session) == 30


async def test_30th_source_allowed(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    channel_route: respx.Route,
    db_session: AsyncSession,
) -> None:
    for i in range(29):
        await _insert_source(db_session, user_id, f"channel_{i:02d}")

    resp = await client.post(URL, json={"input": "@durov_jobs"}, headers=_auth(token))

    assert resp.status_code == 201


async def test_limit_counts_only_own_sources(
    client: httpx.AsyncClient,
    token: str,
    other_registered_user: dict,
    channel_route: respx.Route,
    db_session: AsyncSession,
) -> None:
    other_id = other_registered_user["user"]["id"]
    for i in range(30):
        await _insert_source(db_session, other_id, f"channel_{i:02d}")

    resp = await client.post(URL, json={"input": "@durov_jobs"}, headers=_auth(token))

    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Per-user isolation
# ---------------------------------------------------------------------------


async def test_sources_are_per_user(
    client: httpx.AsyncClient,
    token: str,
    other_registered_user: dict,
    channel_route: respx.Route,
) -> None:
    other_token = other_registered_user["access_token"]
    mine = await client.post(URL, json={"input": "@durov_jobs"}, headers=_auth(token))
    assert mine.status_code == 201

    other_list = await client.get(URL, headers=_auth(other_token))
    assert other_list.json()["sources"] == []

    # The same channel is not a duplicate for another user.
    theirs = await client.post(
        URL, json={"input": "@durov_jobs"}, headers=_auth(other_token)
    )
    assert theirs.status_code == 201
    assert theirs.json()["id"] != mine.json()["id"]


async def test_cannot_delete_another_users_source(
    client: httpx.AsyncClient,
    token: str,
    other_registered_user: dict,
    channel_route: respx.Route,
) -> None:
    source_id = (
        await client.post(URL, json={"input": "@durov_jobs"}, headers=_auth(token))
    ).json()["id"]

    resp = await client.delete(
        f"{URL}/{source_id}", headers=_auth(other_registered_user["access_token"])
    )

    assert resp.status_code == 404
    sources = (await client.get(URL, headers=_auth(token))).json()["sources"]
    assert [s["id"] for s in sources] == [source_id]


# ---------------------------------------------------------------------------
# DELETE /vacancy-sources/{id}
# ---------------------------------------------------------------------------


async def test_delete_source(
    client: httpx.AsyncClient, token: str, channel_route: respx.Route
) -> None:
    source_id = (
        await client.post(URL, json={"input": "@durov_jobs"}, headers=_auth(token))
    ).json()["id"]

    resp = await client.delete(f"{URL}/{source_id}", headers=_auth(token))

    assert resp.status_code == 204
    assert resp.content == b""
    assert (await client.get(URL, headers=_auth(token))).json()["sources"] == []

    again = await client.delete(f"{URL}/{source_id}", headers=_auth(token))
    assert again.status_code == 404


async def test_delete_unknown_id(client: httpx.AsyncClient, token: str) -> None:
    resp = await client.delete(f"{URL}/does-not-exist", headers=_auth(token))
    assert resp.status_code == 404


async def test_readd_after_delete(
    client: httpx.AsyncClient, token: str, channel_route: respx.Route
) -> None:
    source_id = (
        await client.post(URL, json={"input": "@durov_jobs"}, headers=_auth(token))
    ).json()["id"]
    await client.delete(f"{URL}/{source_id}", headers=_auth(token))

    resp = await client.post(
        URL, json={"input": "t.me/durov_jobs"}, headers=_auth(token)
    )

    assert resp.status_code == 201
