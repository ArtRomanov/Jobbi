import httpx
import pytest

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


async def test_create_cv(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    data = await _create_cv(client, token, name="Software Engineer CV")

    assert data["name"] == "Software Engineer CV"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data
    assert data["linked_applications_count"] == 0


async def test_create_cv_with_all_sections(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    payload = {
        "name": "Full CV",
        "personal_info": {
            "full_name": "John Doe",
            "email": "john@example.com",
            "phone": "+1234567890",
            "location": "Berlin, Germany",
            "linkedin_url": "https://linkedin.com/in/johndoe",
        },
        "summary": "Experienced engineer.",
        "work_experience": [
            {
                "company": "TechCorp",
                "role": "Senior Dev",
                "start_date": "2020-01",
                "end_date": "2023-06",
                "is_current": False,
                "description": "Built stuff.",
            }
        ],
        "education": [
            {
                "institution": "MIT",
                "degree": "B.S.",
                "field_of_study": "Computer Science",
                "start_year": "2016",
                "end_year": "2020",
                "description": "Focus on AI.",
            }
        ],
        "skills": "Python, FastAPI, SQLAlchemy",
        "languages": "English, German",
    }
    resp = await client.post(BASE_URL, json=payload, headers=_auth_header(token))
    assert resp.status_code == 201
    data = resp.json()

    assert data["name"] == "Full CV"
    assert data["personal_info"]["full_name"] == "John Doe"
    assert data["personal_info"]["linkedin_url"] == "https://linkedin.com/in/johndoe"
    assert data["summary"] == "Experienced engineer."
    assert len(data["work_experience"]) == 1
    assert data["work_experience"][0]["company"] == "TechCorp"
    assert len(data["education"]) == 1
    assert data["education"][0]["institution"] == "MIT"
    assert data["skills"] == "Python, FastAPI, SQLAlchemy"
    assert data["languages"] == "English, German"


async def test_create_cv_missing_name(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    resp = await client.post(
        BASE_URL, json={"summary": "No name"}, headers=_auth_header(token)
    )
    assert resp.status_code == 422


async def test_list_cvs(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    await _create_cv(client, token, name="CV One")
    await _create_cv(client, token, name="CV Two")

    resp = await client.get(BASE_URL, headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2


async def test_get_cv(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
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


async def test_update_cv(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    created = await _create_cv(client, token, name="Old Name")
    cv_id = created["id"]

    resp = await client.patch(
        f"{BASE_URL}/{cv_id}",
        json={"name": "New Name", "skills": "Rust, Go"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "New Name"
    assert data["skills"] == "Rust, Go"


async def test_delete_cv(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    created = await _create_cv(client, token, name="To Delete")
    cv_id = created["id"]

    resp = await client.delete(f"{BASE_URL}/{cv_id}", headers=_auth_header(token))
    assert resp.status_code == 200
    assert resp.json()["message"] == "CV deleted."

    # Subsequent GET should 404
    resp = await client.get(f"{BASE_URL}/{cv_id}", headers=_auth_header(token))
    assert resp.status_code == 404


async def test_duplicate_cv(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    original = await _create_cv(
        client, token, name="Original", skills="Python", languages="English"
    )
    cv_id = original["id"]

    resp = await client.post(
        f"{BASE_URL}/{cv_id}/duplicate", json={}, headers=_auth_header(token)
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Original (copy)"
    assert data["id"] != original["id"]
    assert data["skills"] == "Python"
    assert data["languages"] == "English"


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
# JSON Validation Tests
# ---------------------------------------------------------------------------


async def test_create_cv_with_work_experience(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    payload = {
        "name": "Work CV",
        "work_experience": [
            {"company": "AlphaCo", "role": "Dev", "is_current": True},
            {"company": "BetaCo", "role": "Intern", "start_date": "2019-06"},
        ],
    }
    resp = await client.post(BASE_URL, json=payload, headers=_auth_header(token))
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["work_experience"]) == 2
    assert data["work_experience"][0]["company"] == "AlphaCo"
    assert data["work_experience"][0]["is_current"] is True
    assert data["work_experience"][1]["company"] == "BetaCo"


async def test_create_cv_with_education(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    payload = {
        "name": "Edu CV",
        "education": [
            {
                "institution": "Stanford",
                "degree": "M.S.",
                "field_of_study": "AI",
            },
            {
                "institution": "Harvard",
                "degree": "B.A.",
            },
        ],
    }
    resp = await client.post(BASE_URL, json=payload, headers=_auth_header(token))
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["education"]) == 2
    assert data["education"][0]["institution"] == "Stanford"
    assert data["education"][1]["institution"] == "Harvard"


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
    resp = await client.delete(
        f"{BASE_URL}/{cv['id']}", headers=_auth_header(token)
    )
    assert resp.status_code == 200

    # Application should now have cv_id = null
    resp = await client.get(
        f"{APP_URL}/{app['id']}", headers=_auth_header(token)
    )
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

    resp = await client.get(
        f"{BASE_URL}/{cv['id']}", headers=_auth_header(token_b)
    )
    assert resp.status_code == 404


async def test_cannot_delete_other_users_cv(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token_a = registered_user["access_token"]
    cv = await _create_cv(client, token_a, name="Protected CV")

    user_b = await _register_user(client, email="userb@example.com")
    token_b = user_b["access_token"]

    resp = await client.delete(
        f"{BASE_URL}/{cv['id']}", headers=_auth_header(token_b)
    )
    assert resp.status_code == 404

    # Verify it still exists for user A
    resp = await client.get(
        f"{BASE_URL}/{cv['id']}", headers=_auth_header(token_a)
    )
    assert resp.status_code == 200
