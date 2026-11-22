"""A CV can only be linked to, shown on, or fed into the chat of an
application owned by the same user (pre-merge 009, blocker)."""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.cv import Cv
from app.services.chat_service import get_application_context

BASE_URL = "/api/v1/applications"
FOREIGN_SECRET = "Top-secret summary of user B"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _make_cv(db: AsyncSession, user_id: str, name: str) -> Cv:
    cv = Cv(user_id=user_id, name=name, summary=FOREIGN_SECRET)
    db.add(cv)
    await db.commit()
    return cv


async def _create_app(client: httpx.AsyncClient, token: str) -> dict:
    resp = await client.post(
        BASE_URL,
        json={"company_name": "Acme", "role_title": "Dev"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def token(registered_user: dict) -> str:
    return registered_user["access_token"]


@pytest.fixture
async def foreign_cv(db_session: AsyncSession, other_registered_user: dict) -> Cv:
    return await _make_cv(db_session, other_registered_user["user"]["id"], "B's CV")


@pytest.mark.parametrize("whose", ["other", "unknown"])
async def test_patch_with_foreign_or_unknown_cv_404_and_nothing_linked(
    client: httpx.AsyncClient,
    token: str,
    foreign_cv: Cv,
    db_session: AsyncSession,
    whose: str,
) -> None:
    app = await _create_app(client, token)
    cv_id = foreign_cv.id if whose == "other" else "no-such-cv"

    resp = await client.patch(
        f"{BASE_URL}/{app['id']}",
        json={"cv_id": cv_id, "notes": "changed"},
        headers=_auth(token),
    )

    assert resp.status_code == 404
    assert resp.json() == {"detail": "CV not found."}
    saved = await db_session.get(Application, app["id"], populate_existing=True)
    assert saved is not None
    assert (saved.cv_id, saved.notes) == (None, None)


async def test_patch_with_own_cv_links_it(
    client: httpx.AsyncClient,
    token: str,
    registered_user: dict,
    db_session: AsyncSession,
) -> None:
    own = await _make_cv(db_session, registered_user["user"]["id"], "My CV")
    app = await _create_app(client, token)

    resp = await client.patch(
        f"{BASE_URL}/{app['id']}", json={"cv_id": own.id}, headers=_auth(token)
    )

    assert resp.status_code == 200
    assert (resp.json()["cv_id"], resp.json()["cv_name"]) == (own.id, "My CV")


async def test_patch_cv_id_null_unlinks(
    client: httpx.AsyncClient,
    token: str,
    registered_user: dict,
    db_session: AsyncSession,
) -> None:
    own = await _make_cv(db_session, registered_user["user"]["id"], "My CV")
    app = await _create_app(client, token)
    await client.patch(
        f"{BASE_URL}/{app['id']}", json={"cv_id": own.id}, headers=_auth(token)
    )

    resp = await client.patch(
        f"{BASE_URL}/{app['id']}", json={"cv_id": None}, headers=_auth(token)
    )

    assert resp.status_code == 200
    assert resp.json()["cv_id"] is None


async def _seed_foreign_link(
    client: httpx.AsyncClient, token: str, db: AsyncSession, cv: Cv
) -> str:
    """Link a foreign CV straight in the DB (legacy rows from before the check)."""
    app = await _create_app(client, token)
    row = await db.get(Application, app["id"])
    assert row is not None
    row.cv_id = cv.id
    await db.commit()
    return app["id"]


async def test_existing_foreign_link_shows_no_cv_name(
    client: httpx.AsyncClient,
    token: str,
    foreign_cv: Cv,
    db_session: AsyncSession,
) -> None:
    app_id = await _seed_foreign_link(client, token, db_session, foreign_cv)

    detail = await client.get(f"{BASE_URL}/{app_id}", headers=_auth(token))
    listing = await client.get(BASE_URL, headers=_auth(token))

    assert detail.json()["cv_name"] is None
    assert [item["cv_name"] for item in listing.json()["items"]] == [None]


async def test_existing_foreign_link_gives_chat_no_cv(
    client: httpx.AsyncClient,
    token: str,
    foreign_cv: Cv,
    db_session: AsyncSession,
) -> None:
    app_id = await _seed_foreign_link(client, token, db_session, foreign_cv)
    application = await db_session.get(Application, app_id)
    assert application is not None

    prompt, _, cv = await get_application_context(db_session, application)

    assert cv is None
    assert FOREIGN_SECRET not in prompt
    assert "B's CV" not in prompt
