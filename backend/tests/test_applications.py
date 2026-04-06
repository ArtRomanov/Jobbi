import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ApplicationStatus
from app.models.application import ApplicationStatusHistory

BASE_URL = "/api/v1/applications"

# Use .value for JSON serialization — str(ApplicationStatus.APPLIED) returns
# "ApplicationStatus.APPLIED", not "applied".
RESEARCHING = ApplicationStatus.RESEARCHING.value
APPLIED = ApplicationStatus.APPLIED.value
INTERVIEW = ApplicationStatus.INTERVIEW.value


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


async def _create_app(
    client: httpx.AsyncClient,
    token: str,
    *,
    company_name: str = "Acme Corp",
    role_title: str = "Backend Engineer",
    **extra: object,
) -> dict:
    payload: dict = {"company_name": company_name, "role_title": role_title, **extra}
    resp = await client.post(
        BASE_URL, json=payload, headers=_auth_header(token)
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# CRUD Tests
# ---------------------------------------------------------------------------


async def test_create_application(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    data = await _create_app(client, token)

    assert data["company_name"] == "Acme Corp"
    assert data["role_title"] == "Backend Engineer"
    assert data["status"] == RESEARCHING
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data
    # Should have initial status history entry
    assert len(data["status_history"]) == 1
    assert data["status_history"][0]["status"] == RESEARCHING


async def test_create_application_with_all_fields(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    payload = {
        "company_name": "MegaCorp",
        "role_title": "Senior Engineer",
        "job_url": "https://example.com/job/123",
        "salary_min": 80000,
        "salary_max": 120000,
        "salary_currency": "USD",
        "contact_name": "Jane Recruiter",
        "contact_email": "jane@megacorp.com",
        "notes": "Referred by a friend",
        "status": APPLIED,
    }
    resp = await client.post(
        BASE_URL, json=payload, headers=_auth_header(token)
    )
    assert resp.status_code == 201
    data = resp.json()

    for field, value in payload.items():
        assert data[field] == value, f"Mismatch on {field}"


async def test_create_application_missing_required(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]

    # Missing role_title
    resp = await client.post(
        BASE_URL,
        json={"company_name": "Acme Corp"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 422

    # Missing company_name
    resp = await client.post(
        BASE_URL,
        json={"role_title": "Engineer"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 422


async def test_list_applications(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    await _create_app(client, token, company_name="Company A")
    await _create_app(client, token, company_name="Company B")

    resp = await client.get(BASE_URL, headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert "page" in data
    assert "per_page" in data


async def test_list_applications_pagination(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    for i in range(3):
        await _create_app(client, token, company_name=f"Company {i}")

    resp = await client.get(
        BASE_URL, params={"page": 1, "per_page": 2}, headers=_auth_header(token)
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["per_page"] == 2


async def test_get_application_detail(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    created = await _create_app(client, token)
    app_id = created["id"]

    resp = await client.get(
        f"{BASE_URL}/{app_id}", headers=_auth_header(token)
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == app_id
    assert "status_history" in data
    assert isinstance(data["status_history"], list)


async def test_update_application(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    created = await _create_app(client, token)
    app_id = created["id"]

    resp = await client.patch(
        f"{BASE_URL}/{app_id}",
        json={"company_name": "Updated Corp", "notes": "New notes"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["company_name"] == "Updated Corp"
    assert data["notes"] == "New notes"
    # Unchanged fields remain
    assert data["role_title"] == "Backend Engineer"


async def test_delete_application(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    created = await _create_app(client, token)
    app_id = created["id"]

    resp = await client.delete(
        f"{BASE_URL}/{app_id}", headers=_auth_header(token)
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Application deleted."

    # Subsequent GET should 404
    resp = await client.get(
        f"{BASE_URL}/{app_id}", headers=_auth_header(token)
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Status History Tests
# ---------------------------------------------------------------------------


async def test_initial_status_history_on_create(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    data = await _create_app(client, token)

    assert len(data["status_history"]) == 1
    entry = data["status_history"][0]
    assert entry["status"] == RESEARCHING


async def test_status_change_creates_history(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    created = await _create_app(client, token)
    app_id = created["id"]

    # Update status
    resp = await client.patch(
        f"{BASE_URL}/{app_id}",
        json={"status": APPLIED},
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == APPLIED

    # Fetch detail separately to get the freshly-loaded status_history
    detail_resp = await client.get(
        f"{BASE_URL}/{app_id}", headers=_auth_header(token)
    )
    data = detail_resp.json()
    assert len(data["status_history"]) == 2

    statuses = {entry["status"] for entry in data["status_history"]}
    assert RESEARCHING in statuses
    assert APPLIED in statuses


async def test_non_status_update_no_new_history(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    created = await _create_app(client, token)
    app_id = created["id"]

    # Update only company_name, not status
    resp = await client.patch(
        f"{BASE_URL}/{app_id}",
        json={"company_name": "Renamed Corp"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["status_history"]) == 1


async def test_status_history_in_detail_response(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    created = await _create_app(client, token)
    app_id = created["id"]

    resp = await client.get(
        f"{BASE_URL}/{app_id}", headers=_auth_header(token)
    )
    data = resp.json()
    entry = data["status_history"][0]
    assert "id" in entry
    assert "status" in entry
    assert "changed_at" in entry


# ---------------------------------------------------------------------------
# Search and Filter Tests
# ---------------------------------------------------------------------------


async def test_search_by_company_name(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    await _create_app(client, token, company_name="Alpha Inc")
    await _create_app(client, token, company_name="Beta LLC")

    resp = await client.get(
        BASE_URL, params={"search": "Alpha"}, headers=_auth_header(token)
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["company_name"] == "Alpha Inc"


async def test_search_by_role_title(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    await _create_app(client, token, role_title="Frontend Developer")
    await _create_app(client, token, role_title="Backend Engineer")

    resp = await client.get(
        BASE_URL, params={"search": "Frontend"}, headers=_auth_header(token)
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["role_title"] == "Frontend Developer"


async def test_search_case_insensitive(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    await _create_app(client, token, company_name="Acme Corp")

    resp = await client.get(
        BASE_URL, params={"search": "acme"}, headers=_auth_header(token)
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    resp = await client.get(
        BASE_URL, params={"search": "ACME"}, headers=_auth_header(token)
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


async def test_filter_by_status(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    await _create_app(client, token, company_name="A", status=APPLIED)
    await _create_app(client, token, company_name="B", status=INTERVIEW)
    await _create_app(client, token, company_name="C", status=APPLIED)

    resp = await client.get(
        BASE_URL,
        params={"status": APPLIED},
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    for item in data["items"]:
        assert item["status"] == APPLIED


async def test_search_no_results(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    await _create_app(client, token)

    resp = await client.get(
        BASE_URL,
        params={"search": "nonexistent-xyz"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


# ---------------------------------------------------------------------------
# Authorization Tests
# ---------------------------------------------------------------------------


async def test_cannot_access_other_users_application(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token_a = registered_user["access_token"]
    created = await _create_app(client, token_a)
    app_id = created["id"]

    # Register a second user
    user_b = await _register_user(client, email="userb@example.com")
    token_b = user_b["access_token"]

    resp = await client.get(
        f"{BASE_URL}/{app_id}", headers=_auth_header(token_b)
    )
    assert resp.status_code == 404


async def test_cannot_update_other_users_application(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token_a = registered_user["access_token"]
    created = await _create_app(client, token_a)
    app_id = created["id"]

    user_b = await _register_user(client, email="userb@example.com")
    token_b = user_b["access_token"]

    resp = await client.patch(
        f"{BASE_URL}/{app_id}",
        json={"company_name": "Hacked"},
        headers=_auth_header(token_b),
    )
    assert resp.status_code == 404


async def test_cannot_delete_other_users_application(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token_a = registered_user["access_token"]
    created = await _create_app(client, token_a)
    app_id = created["id"]

    user_b = await _register_user(client, email="userb@example.com")
    token_b = user_b["access_token"]

    resp = await client.delete(
        f"{BASE_URL}/{app_id}", headers=_auth_header(token_b)
    )
    assert resp.status_code == 404


async def test_list_only_own_applications(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token_a = registered_user["access_token"]
    await _create_app(client, token_a, company_name="User A Corp")

    user_b = await _register_user(client, email="userb@example.com")
    token_b = user_b["access_token"]
    await _create_app(client, token_b, company_name="User B Corp")

    # User A sees only their app
    resp = await client.get(BASE_URL, headers=_auth_header(token_a))
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["company_name"] == "User A Corp"

    # User B sees only their app
    resp = await client.get(BASE_URL, headers=_auth_header(token_b))
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["company_name"] == "User B Corp"


# ---------------------------------------------------------------------------
# History Feed Test
# ---------------------------------------------------------------------------


async def test_history_feed(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    created = await _create_app(client, token, company_name="FeedCo", role_title="Dev")

    # Change status to generate a second history entry
    await client.patch(
        f"{BASE_URL}/{created['id']}",
        json={"status": APPLIED},
        headers=_auth_header(token),
    )

    resp = await client.get(
        f"{BASE_URL}/history", headers=_auth_header(token)
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2

    # Each feed item should contain company_name and role_title
    for item in data["items"]:
        assert item["company_name"] == "FeedCo"
        assert item["role_title"] == "Dev"
        assert "status" in item
        assert "changed_at" in item
        assert "application_id" in item


# ---------------------------------------------------------------------------
# Cascade Delete Test
# ---------------------------------------------------------------------------


async def test_delete_cascades_status_history(
    client: httpx.AsyncClient,
    registered_user: dict,
    db_session: AsyncSession,
) -> None:
    token = registered_user["access_token"]
    created = await _create_app(client, token)
    app_id = created["id"]

    # Add a status change so we have 2 history entries
    await client.patch(
        f"{BASE_URL}/{app_id}",
        json={"status": APPLIED},
        headers=_auth_header(token),
    )

    # Verify history exists before delete
    result = await db_session.execute(
        select(ApplicationStatusHistory).where(
            ApplicationStatusHistory.application_id == app_id
        )
    )
    assert len(result.scalars().all()) == 2

    # Delete the application
    resp = await client.delete(
        f"{BASE_URL}/{app_id}", headers=_auth_header(token)
    )
    assert resp.status_code == 200

    # Verify status history entries are also gone
    result = await db_session.execute(
        select(ApplicationStatusHistory).where(
            ApplicationStatusHistory.application_id == app_id
        )
    )
    assert len(result.scalars().all()) == 0
