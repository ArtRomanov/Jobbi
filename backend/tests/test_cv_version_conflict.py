"""Stale-version guard on CV writes (spec 011 Slice 3): PATCH 409 `CV_CHANGED`
and the reusable `update_cv_content_if_version` helper."""

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import create_app
from app.models.cv import Cv
from app.models.user import User
from app.schemas.cv import CvUpdate
from app.services import cv_service

BASE_URL = "/api/v1/cvs"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_cv(client: httpx.AsyncClient, token: str, **body: object) -> dict:
    resp = await client.post(
        BASE_URL, json={"name": "CV", "content": "Text", **body}, headers=_auth(token)
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def token(registered_user: dict) -> str:
    return registered_user["access_token"]


# ---------------------------------------------------------------------------
# PATCH over HTTP
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"content": "Overwrite"},
        {"name": "Overwrite"},
        {"name": "Renamed", "content": "Other"},
    ],
    ids=["content", "name", "both"],
)
async def test_stale_version_returns_409_and_keeps_the_cv(
    client: httpx.AsyncClient, token: str, body: dict
) -> None:
    cv = await _create_cv(client, token)
    url = f"{BASE_URL}/{cv['id']}"
    saved = await client.patch(
        url,
        json={"name": "Renamed", "content": "New", "version": 1},
        headers=_auth(token),
    )
    assert saved.json()["version"] == 2

    stale = await client.patch(url, json={**body, "version": 1}, headers=_auth(token))

    assert stale.status_code == 409
    assert stale.json() == {"detail": "CV_CHANGED"}
    stored = (await client.get(url, headers=_auth(token))).json()
    assert (stored["name"], stored["content"], stored["version"]) == (
        "Renamed",
        "New",
        2,
    )


@pytest.mark.parametrize("version", [0, 3, 99])
async def test_version_other_than_current_is_rejected(
    client: httpx.AsyncClient, token: str, version: int
) -> None:
    cv = await _create_cv(client, token)
    url = f"{BASE_URL}/{cv['id']}"
    await client.patch(url, json={"content": "v2", "version": 1}, headers=_auth(token))

    resp = await client.patch(
        url, json={"content": "x", "version": version}, headers=_auth(token)
    )

    assert resp.status_code == 409
    assert resp.json() == {"detail": "CV_CHANGED"}


async def test_noop_with_current_version_returns_200_without_bump(
    client: httpx.AsyncClient, token: str
) -> None:
    cv = await _create_cv(client, token)
    url = f"{BASE_URL}/{cv['id']}"
    await client.patch(url, json={"content": "v2", "version": 1}, headers=_auth(token))

    resp = await client.patch(
        url, json={"name": "CV", "content": "v2", "version": 2}, headers=_auth(token)
    )

    assert resp.status_code == 200
    assert resp.json()["version"] == 2


@pytest.mark.parametrize(
    "body",
    [{}, {"name": "CV", "content": "Text"}],
    ids=["empty", "same-values"],
)
async def test_noop_with_stale_version_returns_409(
    client: httpx.AsyncClient, token: str, body: dict
) -> None:
    cv = await _create_cv(client, token)
    url = f"{BASE_URL}/{cv['id']}"
    await client.patch(url, json={"content": "v2", "version": 1}, headers=_auth(token))
    await client.patch(
        url, json={"content": "Text", "version": 2}, headers=_auth(token)
    )

    resp = await client.patch(url, json={**body, "version": 1}, headers=_auth(token))

    assert resp.status_code == 409
    assert resp.json() == {"detail": "CV_CHANGED"}


async def test_other_users_cv_is_404_not_409(
    client: httpx.AsyncClient, token: str, other_registered_user: dict
) -> None:
    cv = await _create_cv(client, token)
    url = f"{BASE_URL}/{cv['id']}"
    other = _auth(other_registered_user["access_token"])

    for version in (1, 7):
        resp = await client.patch(
            url, json={"content": "Hijack", "version": version}, headers=other
        )
        assert resp.status_code == 404

    stored = (await client.get(url, headers=_auth(token))).json()
    assert (stored["content"], stored["version"]) == ("Text", 1)


async def test_missing_cv_is_404(client: httpx.AsyncClient, token: str) -> None:
    resp = await client.patch(
        f"{BASE_URL}/no-such-cv",
        json={"content": "x", "version": 1},
        headers=_auth(token),
    )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# update_cv_content_if_version (reused by the chat card Accept)
# ---------------------------------------------------------------------------


async def _make_cv(db: AsyncSession, user_id: str, **overrides: object) -> Cv:
    cv = Cv(user_id=user_id, name="CV", content="Text", **overrides)
    db.add(cv)
    await db.commit()
    await db.refresh(cv)
    return cv


async def test_helper_writes_and_bumps_version(
    db_session: AsyncSession, make_user
) -> None:
    user = await make_user()
    cv = await _make_cv(db_session, user.id, version=4)

    updated = await cv_service.update_cv_content_if_version(
        db_session, user.id, cv.id, 4, content="New text"
    )
    await db_session.commit()

    assert (updated.name, updated.content, updated.version) == ("CV", "New text", 5)


async def test_helper_does_not_commit(db_session: AsyncSession, make_user) -> None:
    user = await make_user()
    user_id = user.id
    cv = await _make_cv(db_session, user_id)
    cv_id = cv.id

    await cv_service.update_cv_content_if_version(
        db_session, user_id, cv_id, 1, name="Draft"
    )
    await db_session.rollback()
    db_session.expunge_all()

    stored = await cv_service.get_cv(db_session, user_id, cv_id)
    assert (stored.name, stored.version) == ("CV", 1)


async def test_helper_raises_conflict_on_stale_version(
    db_session: AsyncSession, make_user
) -> None:
    user = await make_user()
    cv = await _make_cv(db_session, user.id, version=2)

    with pytest.raises(cv_service.CvVersionConflict):
        await cv_service.update_cv_content_if_version(
            db_session, user.id, cv.id, 1, content="Lost"
        )


async def test_helper_raises_not_found_for_other_user_or_missing(
    db_session: AsyncSession, make_user
) -> None:
    owner = await make_user()
    stranger = await make_user()
    cv = await _make_cv(db_session, owner.id)

    with pytest.raises(cv_service.CvNotFoundError):
        await cv_service.update_cv_content_if_version(
            db_session, stranger.id, cv.id, 1, content="Hijack"
        )
    with pytest.raises(cv_service.CvNotFoundError):
        await cv_service.update_cv_content_if_version(
            db_session, owner.id, "missing", 1, content="x"
        )


# ---------------------------------------------------------------------------
# Concurrent saves (file-backed DB: each session is its own connection)
# ---------------------------------------------------------------------------


@pytest.fixture
async def file_sessions(
    tmp_path: Path,
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'race.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def file_client(
    file_sessions: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[httpx.AsyncClient, None]:
    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with file_sessions() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _seed(sessions: async_sessionmaker[AsyncSession]) -> tuple[User, Cv]:
    async with sessions() as db:
        user = User(email="race@example.com", password_hash="x", full_name="Race")
        db.add(user)
        await db.commit()
        cv = await _make_cv(db, user.id)
    return user, cv


async def test_two_concurrent_saves_one_wins_the_other_gets_409(
    file_client: httpx.AsyncClient,
    file_sessions: async_sessionmaker[AsyncSession],
) -> None:
    user, cv = await _seed(file_sessions)
    url = f"{BASE_URL}/{cv.id}"
    headers = _auth(create_access_token(user.id))

    results = await asyncio.gather(
        file_client.patch(
            url, json={"content": "Tab A", "version": 1}, headers=headers
        ),
        file_client.patch(
            url, json={"content": "Tab B", "version": 1}, headers=headers
        ),
    )

    assert sorted(r.status_code for r in results) == [200, 409]
    loser = next(r for r in results if r.status_code == 409)
    assert loser.json() == {"detail": "CV_CHANGED"}
    winner = next(r for r in results if r.status_code == 200).json()
    async with file_sessions() as db:
        stored = await db.get(Cv, cv.id)
        assert (stored.content, stored.version) == (winner["content"], 2)


async def test_save_racing_past_the_read_check_still_loses(
    file_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Both writers read version 1 before either writes: the conditional UPDATE,
    not the read, is what stops the second one."""
    user, cv = await _seed(file_sessions)

    async with file_sessions() as first, file_sessions() as second:
        assert (await cv_service.get_cv(first, user.id, cv.id)).version == 1
        assert (await cv_service.get_cv(second, user.id, cv.id)).version == 1
        await second.commit()  # end the read transaction, as a request would

        await cv_service.update_cv(
            first, user.id, cv.id, CvUpdate(content="First", version=1)
        )
        with pytest.raises(cv_service.CvVersionConflict):
            await cv_service.update_cv_content_if_version(
                second, user.id, cv.id, 1, content="Second"
            )
        await second.rollback()

    async with file_sessions() as db:
        stored = await db.get(Cv, cv.id)
        assert (stored.content, stored.version) == ("First", 2)
