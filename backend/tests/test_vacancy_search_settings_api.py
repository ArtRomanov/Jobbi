import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vacancy_search_settings import VacancySearchSettings

URL = "/api/v1/vacancy-search-settings"
SOURCES_URL = "/api/v1/vacancy-sources"

DESCRIPTION_TOO_LONG = "Description can be up to 500 characters"
TOO_MANY_TERMS = "You can add up to 50 exclude words"
BAD_TERM = "Exclude words must be 1–64 characters"


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
    assert resp.json() == {"description": "Senior frontend, remote", "exclude": []}
    row = await _stored_row(db_session, user_id)
    assert row is not None
    assert row.description == "Senior frontend, remote"
    assert row.exclude_terms == []


async def test_empty_body_creates_default_row(
    client: httpx.AsyncClient, token: str, user_id: str, db_session: AsyncSession
) -> None:
    resp = await _patch(client, token, {})

    assert resp.status_code == 200
    assert resp.json() == {"description": None, "exclude": []}
    assert await _stored_row(db_session, user_id) is not None


async def test_only_description_keeps_exclude(
    client: httpx.AsyncClient, token: str
) -> None:
    await _patch(client, token, {"description": "Old", "exclude": ["java"]})

    resp = await _patch(client, token, {"description": "New"})

    assert resp.status_code == 200
    assert resp.json() == {"description": "New", "exclude": ["java"]}


async def test_only_exclude_keeps_description(
    client: httpx.AsyncClient, token: str
) -> None:
    await _patch(client, token, {"description": "Frontend", "exclude": ["java"]})

    resp = await _patch(client, token, {"exclude": ["php", "office only"]})

    assert resp.status_code == 200
    assert resp.json() == {"description": "Frontend", "exclude": ["php", "office only"]}


async def test_both_fields_updated(client: httpx.AsyncClient, token: str) -> None:
    await _patch(client, token, {"description": "Old", "exclude": ["java"]})

    resp = await _patch(client, token, {"description": "New", "exclude": ["php"]})

    assert resp.json() == {"description": "New", "exclude": ["php"]}


async def test_null_description_turns_search_off(
    client: httpx.AsyncClient, token: str, user_id: str, db_session: AsyncSession
) -> None:
    await _patch(client, token, {"description": "Frontend", "exclude": ["java"]})

    resp = await _patch(client, token, {"description": None})

    assert resp.json() == {"description": None, "exclude": ["java"]}
    row = await _stored_row(db_session, user_id)
    assert row is not None
    assert row.description is None


async def test_empty_exclude_list_clears_terms(
    client: httpx.AsyncClient, token: str
) -> None:
    await _patch(client, token, {"description": "Frontend", "exclude": ["java"]})

    resp = await _patch(client, token, {"exclude": []})

    assert resp.json() == {"description": "Frontend", "exclude": []}


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
    await _patch(client, token, {"description": "Frontend", "exclude": ["java"]})

    resp = await _patch(client, token, {"description": "a" * 501, "exclude": ["php"]})

    assert resp.status_code == 400
    assert await _get_settings(client, token) == {
        "description": "Frontend",
        "exclude": ["java"],
    }


# --- exclude limits ----------------------------------------------------------


async def test_50_exclude_terms_are_accepted(
    client: httpx.AsyncClient, token: str
) -> None:
    terms = [f"term{i}" for i in range(50)]

    resp = await _patch(client, token, {"exclude": terms})

    assert resp.status_code == 200
    assert resp.json()["exclude"] == terms


async def test_51_exclude_terms_are_rejected(
    client: httpx.AsyncClient, token: str
) -> None:
    resp = await _patch(client, token, {"exclude": [f"term{i}" for i in range(51)]})

    assert resp.status_code == 400
    assert resp.json() == {"detail": TOO_MANY_TERMS}


async def test_limit_counts_terms_after_dedupe(
    client: httpx.AsyncClient, token: str
) -> None:
    terms = [f"term{i}" for i in range(50)] + ["TERM0"]

    resp = await _patch(client, token, {"exclude": terms})

    assert resp.status_code == 200
    assert len(resp.json()["exclude"]) == 50


async def test_term_of_64_chars_is_accepted(
    client: httpx.AsyncClient, token: str
) -> None:
    resp = await _patch(client, token, {"exclude": ["a" * 64]})

    assert resp.status_code == 200
    assert resp.json()["exclude"] == ["a" * 64]


async def test_term_length_is_measured_after_trimming(
    client: httpx.AsyncClient, token: str
) -> None:
    resp = await _patch(client, token, {"exclude": ["  " + "a" * 64 + "  "]})

    assert resp.status_code == 200
    assert resp.json()["exclude"] == ["a" * 64]


@pytest.mark.parametrize("bad_term", ["a" * 65, "", "   ", "\t\n"])
async def test_bad_term_is_rejected(
    client: httpx.AsyncClient, token: str, bad_term: str
) -> None:
    resp = await _patch(client, token, {"exclude": ["java", bad_term]})

    assert resp.status_code == 400
    assert resp.json() == {"detail": BAD_TERM}


async def test_wrong_type_is_validation_error(
    client: httpx.AsyncClient, token: str
) -> None:
    resp = await _patch(client, token, {"exclude": "java"})

    assert resp.status_code == 422


# --- normalisation -----------------------------------------------------------


async def test_terms_are_normalised(client: httpx.AsyncClient, token: str) -> None:
    resp = await _patch(
        client,
        token,
        {"exclude": ["  Java ", "OFFICE   only", "java", "office\tonly", "PHP"]},
    )

    assert resp.status_code == 200
    assert resp.json()["exclude"] == ["java", "office only", "php"]


async def test_cyrillic_terms_are_kept_and_lowercased(
    client: httpx.AsyncClient, token: str
) -> None:
    resp = await _patch(
        client, token, {"exclude": ["Офис", "ТОЛЬКО  офис", "офис", "Ёлка"]}
    )

    assert resp.status_code == 200
    assert resp.json()["exclude"] == ["офис", "только офис", "ёлка"]


# --- reading back, isolation, auth ------------------------------------------


async def test_get_sources_reflects_patch(
    client: httpx.AsyncClient, token: str
) -> None:
    await _patch(client, token, {"description": " Senior React ", "exclude": ["Java"]})

    assert await _get_settings(client, token) == {
        "description": "Senior React",
        "exclude": ["java"],
    }


async def test_settings_are_per_user(
    client: httpx.AsyncClient, token: str, other_registered_user: dict
) -> None:
    other_token = other_registered_user["access_token"]
    await _patch(client, token, {"description": "Mine", "exclude": ["java"]})

    assert await _get_settings(client, other_token) == {
        "description": None,
        "exclude": [],
    }

    resp = await _patch(client, other_token, {"exclude": ["php"]})

    assert resp.json() == {"description": None, "exclude": ["php"]}
    assert await _get_settings(client, token) == {
        "description": "Mine",
        "exclude": ["java"],
    }


async def test_requires_auth(client: httpx.AsyncClient) -> None:
    resp = await client.patch(URL, json={"description": "x"})

    # HTTPBearer answers 403 on older FastAPI, 401 on newer.
    assert resp.status_code in (401, 403)
