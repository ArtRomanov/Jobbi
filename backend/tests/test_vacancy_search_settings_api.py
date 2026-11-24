import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vacancy_search_settings import VacancySearchSettings

URL = "/api/v1/vacancy-search-settings"
SOURCES_URL = "/api/v1/vacancy-sources"

DESCRIPTION_TOO_LONG = "Description can be up to 500 characters"
TOO_MANY_KEYWORDS = "You can add up to 50 keywords"
BAD_KEYWORD = "Keywords must be 1–64 characters"


def _settings(
    description: str | None = None,
    keywords: list[str] | None = None,
    keyword_filter: bool = True,
) -> dict:
    """The settings read shape (defaults: no keywords, filter switch on)."""
    return {
        "description": description,
        "keywords": keywords or [],
        "keyword_filter": keyword_filter,
    }


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
    assert resp.json() == _settings("Senior frontend, remote")
    row = await _stored_row(db_session, user_id)
    assert row is not None
    assert row.description == "Senior frontend, remote"


async def test_empty_body_creates_default_row(
    client: httpx.AsyncClient, token: str, user_id: str, db_session: AsyncSession
) -> None:
    resp = await _patch(client, token, {})

    assert resp.status_code == 200
    assert resp.json() == _settings(None)
    assert await _stored_row(db_session, user_id) is not None


async def test_null_description_turns_search_off(
    client: httpx.AsyncClient, token: str, user_id: str, db_session: AsyncSession
) -> None:
    await _patch(client, token, {"description": "Frontend"})

    resp = await _patch(client, token, {"description": None})

    assert resp.json() == _settings(None)
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
    assert await _get_settings(client, token) == _settings("Frontend")


# --- exclude words are gone (backlog #12) -------------------------------------


async def test_exclude_from_an_old_client_is_ignored(
    client: httpx.AsyncClient, token: str
) -> None:
    resp = await _patch(
        client, token, {"description": "Frontend", "exclude": ["java", "x" * 500]}
    )

    assert resp.status_code == 200
    assert resp.json() == _settings("Frontend")
    assert await _get_settings(client, token) == _settings("Frontend")


async def test_exclude_only_body_changes_nothing(
    client: httpx.AsyncClient, token: str
) -> None:
    await _patch(client, token, {"description": "Frontend"})

    resp = await _patch(client, token, {"exclude": "java"})

    assert resp.status_code == 200
    assert resp.json() == _settings("Frontend")


# --- keyword filter ----------------------------------------------------------


async def test_keywords_and_switch_saved_together(
    client: httpx.AsyncClient, token: str, user_id: str, db_session: AsyncSession
) -> None:
    resp = await _patch(
        client,
        token,
        {
            "description": "Frontend",
            "keywords": ["react", "фронт"],
            "keyword_filter": False,
        },
    )

    assert resp.status_code == 200
    assert resp.json() == _settings("Frontend", ["react", "фронт"], False)
    row = await _stored_row(db_session, user_id)
    assert row is not None
    assert (row.keywords, row.keyword_filter_enabled) == (["react", "фронт"], False)


async def test_only_description_keeps_keywords_and_switch(
    client: httpx.AsyncClient, token: str
) -> None:
    await _patch(client, token, {"keywords": ["react"], "keyword_filter": False})

    resp = await _patch(client, token, {"description": "New"})

    assert resp.json() == _settings("New", ["react"], False)


async def test_only_keywords_keep_description_and_switch(
    client: httpx.AsyncClient, token: str
) -> None:
    await _patch(client, token, {"description": "Frontend", "keyword_filter": False})

    resp = await _patch(client, token, {"keywords": ["node", "next.js"]})

    assert resp.json() == _settings("Frontend", ["node", "next.js"], False)


async def test_only_switch_keeps_keywords(
    client: httpx.AsyncClient, token: str
) -> None:
    await _patch(client, token, {"description": "Frontend", "keywords": ["react"]})

    resp = await _patch(client, token, {"keyword_filter": False})

    assert resp.json() == _settings("Frontend", ["react"], False)


async def test_empty_keyword_list_clears_keywords(
    client: httpx.AsyncClient, token: str
) -> None:
    await _patch(client, token, {"keywords": ["react"]})

    resp = await _patch(client, token, {"keywords": []})

    assert resp.json()["keywords"] == []


async def test_keywords_are_normalised(client: httpx.AsyncClient, token: str) -> None:
    resp = await _patch(
        client,
        token,
        {"keywords": ["  React ", "FRONT   end", "react", "front\tend", "Фронт"]},
    )

    assert resp.status_code == 200
    assert resp.json()["keywords"] == ["react", "front end", "фронт"]


async def test_50_keywords_are_accepted(client: httpx.AsyncClient, token: str) -> None:
    keywords = [f"kw{i}" for i in range(50)]

    resp = await _patch(client, token, {"keywords": keywords})

    assert resp.status_code == 200
    assert resp.json()["keywords"] == keywords


async def test_51_keywords_are_rejected(client: httpx.AsyncClient, token: str) -> None:
    resp = await _patch(client, token, {"keywords": [f"kw{i}" for i in range(51)]})

    assert resp.status_code == 400
    assert resp.json() == {"detail": TOO_MANY_KEYWORDS}


async def test_keyword_limit_counts_after_dedupe(
    client: httpx.AsyncClient, token: str
) -> None:
    keywords = [f"kw{i}" for i in range(50)] + ["KW0"]

    resp = await _patch(client, token, {"keywords": keywords})

    assert resp.status_code == 200
    assert len(resp.json()["keywords"]) == 50


async def test_keyword_of_64_chars_after_trimming_is_accepted(
    client: httpx.AsyncClient, token: str
) -> None:
    resp = await _patch(client, token, {"keywords": ["  " + "a" * 64 + "  "]})

    assert resp.status_code == 200
    assert resp.json()["keywords"] == ["a" * 64]


@pytest.mark.parametrize("bad", ["a" * 65, "", "   ", "\t\n"])
async def test_bad_keyword_is_rejected_and_nothing_saved(
    client: httpx.AsyncClient, token: str, bad: str
) -> None:
    await _patch(client, token, {"description": "Frontend", "keywords": ["react"]})

    resp = await _patch(
        client, token, {"description": "Other", "keywords": ["node", bad]}
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": BAD_KEYWORD}
    assert await _get_settings(client, token) == _settings("Frontend", ["react"])


@pytest.mark.parametrize(
    "body",
    [
        {"keywords": "react"},
        {"keywords": [1]},
        {"keywords": None},
        {"keyword_filter": "yes"},
        {"keyword_filter": 1},
        {"keyword_filter": None},
    ],
)
async def test_wrong_type_is_validation_error(
    client: httpx.AsyncClient, token: str, body: dict
) -> None:
    resp = await _patch(client, token, body)

    assert resp.status_code == 422


# --- reading back, isolation, auth ------------------------------------------


async def test_get_sources_reflects_patch(
    client: httpx.AsyncClient, token: str
) -> None:
    await _patch(client, token, {"description": " Senior React "})

    assert await _get_settings(client, token) == _settings("Senior React")


async def test_settings_are_per_user(
    client: httpx.AsyncClient, token: str, other_registered_user: dict
) -> None:
    other_token = other_registered_user["access_token"]
    await _patch(client, token, {"description": "Mine"})

    assert await _get_settings(client, other_token) == _settings(None)

    resp = await _patch(client, other_token, {"description": "Theirs"})

    assert resp.json() == _settings("Theirs")
    assert await _get_settings(client, token) == _settings("Mine")


async def test_requires_auth(client: httpx.AsyncClient) -> None:
    resp = await client.patch(URL, json={"description": "x"})

    # HTTPBearer answers 403 on older FastAPI, 401 on newer.
    assert resp.status_code in (401, 403)
