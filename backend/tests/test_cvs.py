import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cv import Cv
from app.services.cv_service import build_cv_copy

BASE_URL = "/api/v1/cvs"
APP_URL = "/api/v1/applications"


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _register_user(
    client: httpx.AsyncClient,
    email: str = "testuser@example.com",
    password: str = "securepassword123",
    full_name: str = "Test User",
) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )
    assert resp.status_code == 201
    return resp.json()


async def _create_cv(
    client: httpx.AsyncClient,
    token: str,
    *,
    name: str = "My CV",
    **extra: object,
) -> dict:
    payload: dict = {"name": name, **extra}
    resp = await client.post(BASE_URL, json=payload, headers=_auth_header(token))
    assert resp.status_code == 201
    return resp.json()


async def _create_app(
    client: httpx.AsyncClient,
    token: str,
    *,
    company_name: str = "Acme Corp",
    role_title: str = "Backend Engineer",
    **extra: object,
) -> dict:
    payload: dict = {"company_name": company_name, "role_title": role_title, **extra}
    resp = await client.post(APP_URL, json=payload, headers=_auth_header(token))
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# CRUD Tests
# ---------------------------------------------------------------------------


async def test_create_cv(client: httpx.AsyncClient, registered_user: dict) -> None:
    token = registered_user["access_token"]
    data = await _create_cv(client, token, name="Software Engineer CV")

    assert data["name"] == "Software Engineer CV"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data
    assert data["linked_applications_count"] == 0


async def test_create_cv_with_content(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    content = "# John Doe\njohn@example.com\n\n## Skills\nPython, FastAPI"

    data = await _create_cv(client, token, name="  Full CV  ", content=content)

    assert data["name"] == "Full CV"
    assert data["content"] == content
    assert data["version"] == 1
    assert "personal_info" not in data


async def test_create_cv_content_defaults_to_empty(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    data = await _create_cv(client, registered_user["access_token"])

    assert data["content"] == ""
    assert data["version"] == 1


async def test_create_cv_missing_name(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    resp = await client.post(
        BASE_URL, json={"content": "No name"}, headers=_auth_header(token)
    )
    assert resp.status_code == 422


async def test_list_cvs(client: httpx.AsyncClient, registered_user: dict) -> None:
    token = registered_user["access_token"]
    await _create_cv(client, token, name="CV One")
    await _create_cv(client, token, name="CV Two")

    resp = await client.get(BASE_URL, headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2


async def test_get_cv(client: httpx.AsyncClient, registered_user: dict) -> None:
    token = registered_user["access_token"]
    created = await _create_cv(client, token, name="Detail CV")
    cv_id = created["id"]

    resp = await client.get(f"{BASE_URL}/{cv_id}", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == cv_id
    assert data["name"] == "Detail CV"
    assert "created_at" in data
    assert "updated_at" in data


async def test_update_cv(client: httpx.AsyncClient, registered_user: dict) -> None:
    token = registered_user["access_token"]
    created = await _create_cv(client, token, name="Old Name")
    cv_id = created["id"]

    resp = await client.patch(
        f"{BASE_URL}/{cv_id}",
        json={"name": "New Name", "content": "## Skills\nRust, Go", "version": 1},
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "New Name"
    assert data["content"] == "## Skills\nRust, Go"
    assert data["version"] == 2


@pytest.mark.parametrize(
    "body",
    [{"name": "Renamed"}, {"content": "New text"}],
    ids=["name", "content"],
)
async def test_update_bumps_version_by_one_per_change(
    client: httpx.AsyncClient, registered_user: dict, body: dict
) -> None:
    token = registered_user["access_token"]
    cv = await _create_cv(client, token, name="CV", content="Old text")
    url = f"{BASE_URL}/{cv['id']}"

    first = await client.patch(
        url, json={**body, "version": 1}, headers=_auth_header(token)
    )
    again = await client.patch(
        url, json={"name": "Second", "version": 2}, headers=_auth_header(token)
    )

    assert first.json()["version"] == 2
    assert again.json()["version"] == 3
    stored = await client.get(url, headers=_auth_header(token))
    assert stored.json()["version"] == 3


@pytest.mark.parametrize(
    "body",
    [
        {"version": 1},
        {"name": "CV", "content": "Text", "version": 1},
        {"name": None, "content": None, "version": 1},
    ],
    ids=["nothing", "same-values", "nulls"],
)
async def test_update_without_a_change_keeps_version(
    client: httpx.AsyncClient, registered_user: dict, body: dict
) -> None:
    token = registered_user["access_token"]
    cv = await _create_cv(client, token, name="CV", content="Text")

    resp = await client.patch(
        f"{BASE_URL}/{cv['id']}", json=body, headers=_auth_header(token)
    )

    assert resp.status_code == 200
    assert resp.json()["version"] == 1
    assert resp.json()["name"] == "CV"
    assert resp.json()["content"] == "Text"


async def test_update_requires_version(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    cv = await _create_cv(client, token)

    resp = await client.patch(
        f"{BASE_URL}/{cv['id']}", json={"name": "X"}, headers=_auth_header(token)
    )

    assert resp.status_code == 422


async def test_delete_cv(client: httpx.AsyncClient, registered_user: dict) -> None:
    token = registered_user["access_token"]
    created = await _create_cv(client, token, name="To Delete")
    cv_id = created["id"]

    resp = await client.delete(f"{BASE_URL}/{cv_id}", headers=_auth_header(token))
    assert resp.status_code == 200
    assert resp.json()["message"] == "CV deleted."

    # Subsequent GET should 404
    resp = await client.get(f"{BASE_URL}/{cv_id}", headers=_auth_header(token))
    assert resp.status_code == 404


async def test_duplicate_cv(client: httpx.AsyncClient, registered_user: dict) -> None:
    token = registered_user["access_token"]
    original = await _create_cv(
        client, token, name="Original", content="## Skills\nPython"
    )
    cv_id = original["id"]

    resp = await client.post(
        f"{BASE_URL}/{cv_id}/duplicate", json={}, headers=_auth_header(token)
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Original (copy)"
    assert data["id"] != original["id"]
    assert data["content"] == "## Skills\nPython"
    assert data["version"] == 1


async def test_duplicate_cv_custom_name(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    original = await _create_cv(client, token, name="Base CV")
    cv_id = original["id"]

    resp = await client.post(
        f"{BASE_URL}/{cv_id}/duplicate",
        json={"name": "Custom Copy"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Custom Copy"


# ---------------------------------------------------------------------------
# Validation Tests
# ---------------------------------------------------------------------------


async def test_content_up_to_20000_chars_is_accepted(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    content = "a" * 19_999 + "\n"

    data = await _create_cv(client, token, content=content)
    resp = await client.patch(
        f"{BASE_URL}/{data['id']}",
        json={"content": "b" * 20_000, "version": 1},
        headers=_auth_header(token),
    )

    assert len(data["content"]) == 20_000
    assert resp.status_code == 200


async def test_content_over_20000_chars_is_rejected(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    cv = await _create_cv(client, token, content="Keep me")

    create = await client.post(
        BASE_URL,
        json={"name": "Too long", "content": "a" * 20_001},
        headers=_auth_header(token),
    )
    update = await client.patch(
        f"{BASE_URL}/{cv['id']}",
        json={"content": "a" * 20_001, "version": 1},
        headers=_auth_header(token),
    )

    assert create.status_code == 422
    assert update.status_code == 422
    stored = await client.get(f"{BASE_URL}/{cv['id']}", headers=_auth_header(token))
    assert stored.json()["content"] == "Keep me"


@pytest.mark.parametrize("name", ["", "   ", "\t\n "])
async def test_empty_or_whitespace_name_is_rejected(
    client: httpx.AsyncClient, registered_user: dict, name: str
) -> None:
    token = registered_user["access_token"]
    cv = await _create_cv(client, token)

    create = await client.post(
        BASE_URL, json={"name": name}, headers=_auth_header(token)
    )
    update = await client.patch(
        f"{BASE_URL}/{cv['id']}",
        json={"name": name, "version": 1},
        headers=_auth_header(token),
    )

    assert create.status_code == 422
    assert update.status_code == 422


async def test_name_limit_is_255_chars(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]

    ok = await client.post(
        BASE_URL, json={"name": "n" * 255}, headers=_auth_header(token)
    )
    too_long = await client.post(
        BASE_URL, json={"name": "n" * 256}, headers=_auth_header(token)
    )

    assert ok.status_code == 201
    assert too_long.status_code == 422


async def test_build_cv_copy_copies_content(
    registered_user: dict, db_session: AsyncSession
) -> None:
    user_id = registered_user["user"]["id"]
    original = Cv(user_id=user_id, name="Base", content="## Summary\nHello", version=4)
    db_session.add(original)
    await db_session.commit()

    copy = await build_cv_copy(db_session, user_id, original.id, "Copy")
    await db_session.commit()

    assert copy.id != original.id
    assert copy.name == "Copy"
    assert copy.content == "## Summary\nHello"
    assert copy.version == 1


# ---------------------------------------------------------------------------
# Application Linking Tests
# ---------------------------------------------------------------------------


async def test_link_cv_to_application(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    cv = await _create_cv(client, token, name="Linked CV")
    app = await _create_app(client, token)

    resp = await client.patch(
        f"{APP_URL}/{app['id']}",
        json={"cv_id": cv["id"]},
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["cv_id"] == cv["id"]
    assert data["cv_name"] == "Linked CV"


async def test_unlink_cv_from_application(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    cv = await _create_cv(client, token, name="Temp CV")
    app = await _create_app(client, token)

    # Link first
    await client.patch(
        f"{APP_URL}/{app['id']}",
        json={"cv_id": cv["id"]},
        headers=_auth_header(token),
    )

    # Unlink
    resp = await client.patch(
        f"{APP_URL}/{app['id']}",
        json={"cv_id": None},
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["cv_id"] is None
    assert data["cv_name"] is None


async def test_delete_cv_sets_null_on_applications(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    cv = await _create_cv(client, token, name="Soon Deleted")
    app = await _create_app(client, token)

    # Link cv to application
    await client.patch(
        f"{APP_URL}/{app['id']}",
        json={"cv_id": cv["id"]},
        headers=_auth_header(token),
    )

    # Delete the CV
    resp = await client.delete(f"{BASE_URL}/{cv['id']}", headers=_auth_header(token))
    assert resp.status_code == 200

    # Application should now have cv_id = null
    resp = await client.get(f"{APP_URL}/{app['id']}", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["cv_id"] is None
    assert data["cv_name"] is None


async def test_cv_linked_applications_count(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    cv = await _create_cv(client, token, name="Counted CV")

    # Link two applications to this CV
    app1 = await _create_app(client, token, company_name="Co1")
    app2 = await _create_app(client, token, company_name="Co2")

    await client.patch(
        f"{APP_URL}/{app1['id']}",
        json={"cv_id": cv["id"]},
        headers=_auth_header(token),
    )
    await client.patch(
        f"{APP_URL}/{app2['id']}",
        json={"cv_id": cv["id"]},
        headers=_auth_header(token),
    )

    # List CVs and check count
    resp = await client.get(BASE_URL, headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["linked_applications_count"] == 2


# ---------------------------------------------------------------------------
# Authorization Tests
# ---------------------------------------------------------------------------


async def test_cannot_access_other_users_cv(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token_a = registered_user["access_token"]
    cv = await _create_cv(client, token_a, name="Private CV")

    user_b = await _register_user(client, email="userb@example.com")
    token_b = user_b["access_token"]

    resp = await client.get(f"{BASE_URL}/{cv['id']}", headers=_auth_header(token_b))
    assert resp.status_code == 404


async def test_cannot_delete_other_users_cv(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token_a = registered_user["access_token"]
    cv = await _create_cv(client, token_a, name="Protected CV")

    user_b = await _register_user(client, email="userb@example.com")
    token_b = user_b["access_token"]

    resp = await client.delete(f"{BASE_URL}/{cv['id']}", headers=_auth_header(token_b))
    assert resp.status_code == 404

    # Verify it still exists for user A
    resp = await client.get(f"{BASE_URL}/{cv['id']}", headers=_auth_header(token_a))
    assert resp.status_code == 200
