import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vacancy_search_settings import VacancySearchSettings

URL = "/api/v1/vacancy-search-settings"
SOURCES_URL = "/api/v1/vacancy-sources"

DESCRIPTION_TOO_LONG = "Description can be up to 500 characters"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def token(registered_user: dict) -> str:
    return registered_user["access_token"]


@pytest.fixture
def user_id(registered_user: dict) -> str:
    return registered_user["user"]["id"]


async def _patch(client: httpx.AsyncClient, token: str, body: dict) -> httpx.Response:
    return await client.patch(URL, json=body, headers=_auth(token))


async def _get_settings(client: httpx.AsyncClient, token: str) -> dict:
    resp = await client.get(SOURCES_URL, headers=_auth(token))
    assert resp.status_code == 200
    return resp.json()["settings"]


async def _stored_row(db: AsyncSession, user_id: str) -> VacancySearchSettings | None:
    result = await db.execute(
        select(VacancySearchSettings).where(VacancySearchSettings.user_id == user_id)
    )
    return result.scalar_one_or_none()


# --- creating and partial updates --------------------------------------------


async def test_first_patch_creates_row(
    client: httpx.AsyncClient, token: str, user_id: str, db_session: AsyncSession
) -> None:
    resp = await _patch(client, token, {"description": "Senior frontend, remote"})

    assert resp.status_code == 200
    assert resp.json() == {"description": "Senior frontend, remote"}
    row = await _stored_row(db_session, user_id)
    assert row is not None
    assert row.description == "Senior frontend, remote"


async def test_empty_body_creates_default_row(
    client: httpx.AsyncClient, token: str, user_id: str, db_session: AsyncSession
) -> None:
    resp = await _patch(client, token, {})

    assert resp.status_code == 200
    assert resp.json() == {"description": None}
    assert await _stored_row(db_session, user_id) is not None


async def test_null_description_turns_search_off(
    client: httpx.AsyncClient, token: str, user_id: str, db_session: AsyncSession
) -> None:
    await _patch(client, token, {"description": "Frontend"})

    resp = await _patch(client, token, {"description": None})

    assert resp.json() == {"description": None}
    row = await _stored_row(db_session, user_id)
    assert row is not None
    assert row.description is None


@pytest.mark.parametrize("blank", ["", "   ", "\n\t  "])
async def test_blank_description_is_stored_as_null(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    db_session: AsyncSession,
    blank: str,
) -> None:
    await _patch(client, token, {"description": "Frontend"})

    resp = await _patch(client, token, {"description": blank})

    assert resp.status_code == 200
    assert resp.json()["description"] is None
    row = await _stored_row(db_session, user_id)
    assert row is not None
    assert row.description is None


async def test_description_is_trimmed(client: httpx.AsyncClient, token: str) -> None:
    resp = await _patch(client, token, {"description": "  React,\nremote  "})

    assert resp.json()["description"] == "React,\nremote"


# --- description limit -------------------------------------------------------


async def test_description_of_500_chars_is_accepted(
    client: httpx.AsyncClient, token: str
) -> None:
    resp = await _patch(client, token, {"description": "a" * 500})

    assert resp.status_code == 200
    assert resp.json()["description"] == "a" * 500


async def test_description_of_501_chars_is_rejected(
    client: httpx.AsyncClient, token: str, user_id: str, db_session: AsyncSession
) -> None:
    resp = await _patch(client, token, {"description": "a" * 501})

    assert resp.status_code == 400
    assert resp.json() == {"detail": DESCRIPTION_TOO_LONG}
    assert await _stored_row(db_session, user_id) is None


async def test_rejected_patch_keeps_previous_values(
    client: httpx.AsyncClient, token: str
) -> None:
    await _patch(client, token, {"description": "Frontend"})

    resp = await _patch(client, token, {"description": "a" * 501})

    assert resp.status_code == 400
    assert await _get_settings(client, token) == {"description": "Frontend"}


# --- exclude words are gone (backlog #12) -------------------------------------


async def test_exclude_from_an_old_client_is_ignored(
    client: httpx.AsyncClient, token: str
) -> None:
    resp = await _patch(
        client, token, {"description": "Frontend", "exclude": ["java", "x" * 500]}
    )

    assert resp.status_code == 200
    assert resp.json() == {"description": "Frontend"}
    assert await _get_settings(client, token) == {"description": "Frontend"}


async def test_exclude_only_body_changes_nothing(
    client: httpx.AsyncClient, token: str
) -> None:
    await _patch(client, token, {"description": "Frontend"})

    resp = await _patch(client, token, {"exclude": "java"})

    assert resp.status_code == 200
    assert resp.json() == {"description": "Frontend"}


# --- reading back, isolation, auth ------------------------------------------


async def test_get_sources_reflects_patch(
    client: httpx.AsyncClient, token: str
) -> None:
    await _patch(client, token, {"description": " Senior React "})

    assert await _get_settings(client, token) == {"description": "Senior React"}


async def test_settings_are_per_user(
    client: httpx.AsyncClient, token: str, other_registered_user: dict
) -> None:
    other_token = other_registered_user["access_token"]
    await _patch(client, token, {"description": "Mine"})

    assert await _get_settings(client, other_token) == {"description": None}

    resp = await _patch(client, other_token, {"description": "Theirs"})

    assert resp.json() == {"description": "Theirs"}
    assert await _get_settings(client, token) == {"description": "Mine"}


async def test_requires_auth(client: httpx.AsyncClient) -> None:
    resp = await client.patch(URL, json={"description": "x"})

    # HTTPBearer answers 403 on older FastAPI, 401 on newer.
    assert resp.status_code in (401, 403)
