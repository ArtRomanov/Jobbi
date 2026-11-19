import re
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import telegram_service
from app.services.telegram_service import get_user_link, verify_and_consume_code

CHAT_ID = 987_654_321
# Timestamps must carry an explicit UTC marker so browsers don't read them as local.
UTC_SUFFIX = re.compile(r"(Z|\+00:00)$")


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _link_via_code(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    token: str,
    chat_id: int = CHAT_ID,
    username: str | None = "tg_user",
) -> None:
    """Simulate the bot side: generate a code over the API and consume it."""
    resp = await client.post(
        "/api/v1/telegram/connection-code", headers=_auth_header(token)
    )
    assert resp.status_code == 201
    link = await verify_and_consume_code(
        db_session, resp.json()["code"], chat_id, username
    )
    assert link is not None


# ---------------------------------------------------------------------------
# POST /telegram/connection-code
# ---------------------------------------------------------------------------


async def test_connection_code_created(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    before = datetime.now(timezone.utc).replace(tzinfo=None)

    resp = await client.post(
        "/api/v1/telegram/connection-code",
        headers=_auth_header(registered_user["access_token"]),
    )

    assert resp.status_code == 201
    data = resp.json()
    assert re.fullmatch(r"[A-Z0-9]{6}", data["code"])
    assert UTC_SUFFIX.search(data["expires_at"])
    expires_at = datetime.fromisoformat(data["expires_at"])
    assert expires_at.utcoffset() == timedelta(0)
    expires_at = expires_at.replace(tzinfo=None)
    assert timedelta(minutes=9) < expires_at - before <= timedelta(minutes=10, seconds=5)


async def test_connection_code_invalidates_prior(
    client: httpx.AsyncClient, registered_user: dict, db_session: AsyncSession
) -> None:
    headers = _auth_header(registered_user["access_token"])
    first = (await client.post("/api/v1/telegram/connection-code", headers=headers)).json()
    second = (
        await client.post("/api/v1/telegram/connection-code", headers=headers)
    ).json()

    assert await verify_and_consume_code(db_session, first["code"], CHAT_ID, None) is None
    assert await verify_and_consume_code(db_session, second["code"], CHAT_ID, None)


async def test_connection_code_generation_failure_returns_503(
    client: httpx.AsyncClient,
    registered_user: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(telegram_service, "_generate_code", lambda: "ABC123")
    headers = _auth_header(registered_user["access_token"])
    other = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "holder@example.com",
            "password": "holderpassword123",
            "full_name": "Code Holder",
        },
    )
    await client.post(
        "/api/v1/telegram/connection-code",
        headers=_auth_header(other.json()["access_token"]),
    )

    resp = await client.post("/api/v1/telegram/connection-code", headers=headers)

    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /telegram/status
# ---------------------------------------------------------------------------


async def test_status_not_connected(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    resp = await client.get(
        "/api/v1/telegram/status",
        headers=_auth_header(registered_user["access_token"]),
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "connected": False,
        "telegram_username": None,
        "linked_at": None,
    }


async def test_status_connected(
    client: httpx.AsyncClient, registered_user: dict, db_session: AsyncSession
) -> None:
    token = registered_user["access_token"]
    await _link_via_code(client, db_session, token, username="alice_tg")

    resp = await client.get("/api/v1/telegram/status", headers=_auth_header(token))

    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is True
    assert data["telegram_username"] == "alice_tg"
    assert UTC_SUFFIX.search(data["linked_at"])
    assert datetime.fromisoformat(data["linked_at"]).utcoffset() == timedelta(0)


# ---------------------------------------------------------------------------
# DELETE /telegram/link
# ---------------------------------------------------------------------------


async def test_disconnect_removes_link(
    client: httpx.AsyncClient, registered_user: dict, db_session: AsyncSession
) -> None:
    token = registered_user["access_token"]
    await _link_via_code(client, db_session, token)

    resp = await client.delete("/api/v1/telegram/link", headers=_auth_header(token))

    assert resp.status_code == 200
    status_resp = await client.get(
        "/api/v1/telegram/status", headers=_auth_header(token)
    )
    assert status_resp.json()["connected"] is False


async def test_disconnect_when_not_linked_is_ok(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    resp = await client.delete(
        "/api/v1/telegram/link",
        headers=_auth_header(registered_user["access_token"]),
    )

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/telegram/connection-code"),
        ("GET", "/api/v1/telegram/status"),
        ("DELETE", "/api/v1/telegram/link"),
    ],
)
async def test_endpoints_require_auth(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    resp = await client.request(method, path)

    assert resp.status_code == 401


async def test_user_cannot_affect_another_users_link(
    client: httpx.AsyncClient,
    registered_user: dict,
    other_registered_user: dict,
    db_session: AsyncSession,
) -> None:
    owner_token = registered_user["access_token"]
    intruder_headers = _auth_header(other_registered_user["access_token"])
    await _link_via_code(client, db_session, owner_token)

    status_resp = await client.get("/api/v1/telegram/status", headers=intruder_headers)
    delete_resp = await client.delete("/api/v1/telegram/link", headers=intruder_headers)

    assert status_resp.json()["connected"] is False
    assert delete_resp.status_code == 200
    assert await get_user_link(db_session, registered_user["user"]["id"]) is not None
    owner_status = await client.get(
        "/api/v1/telegram/status", headers=_auth_header(owner_token)
    )
    assert owner_status.json()["connected"] is True


async def test_new_code_does_not_invalidate_other_users_code(
    client: httpx.AsyncClient,
    registered_user: dict,
    other_registered_user: dict,
    db_session: AsyncSession,
) -> None:
    owner_code = (
        await client.post(
            "/api/v1/telegram/connection-code",
            headers=_auth_header(registered_user["access_token"]),
        )
    ).json()["code"]

    await client.post(
        "/api/v1/telegram/connection-code",
        headers=_auth_header(other_registered_user["access_token"]),
    )

    link = await verify_and_consume_code(db_session, owner_code, CHAT_ID, None)
    assert link is not None
    assert link.user_id == registered_user["user"]["id"]
