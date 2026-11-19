import httpx
import pytest


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# GET /users/me
# ---------------------------------------------------------------------------


async def test_get_me_authenticated(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    resp = await client.get("/api/v1/users/me", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "testuser@example.com"
    assert data["full_name"] == "Test User"
    assert "id" in data


async def test_get_me_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# PATCH /users/me
# ---------------------------------------------------------------------------


async def test_update_me_name(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    resp = await client.patch(
        "/api/v1/users/me",
        headers=_auth_header(token),
        json={"full_name": "Updated Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Updated Name"


async def test_update_me_preferences(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    resp = await client.patch(
        "/api/v1/users/me",
        headers=_auth_header(token),
        json={
            "desired_role": "Backend Engineer",
            "desired_location": "Berlin",
            "remote_preference": "remote",
            "salary_min": 70000,
            "salary_max": 100000,
            "salary_currency": "EUR",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["desired_role"] == "Backend Engineer"
    assert data["desired_location"] == "Berlin"
    assert data["remote_preference"] == "remote"
    assert data["salary_min"] == 70000
    assert data["salary_max"] == 100000
    assert data["salary_currency"] == "EUR"


async def test_update_me_email_not_editable(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    resp = await client.patch(
        "/api/v1/users/me",
        headers=_auth_header(token),
        json={"email": "hacker@evil.com", "full_name": "Same Name"},
    )
    assert resp.status_code == 200
    # Email must remain the original value (UserUpdate schema excludes email)
    assert resp.json()["email"] == "testuser@example.com"


# ---------------------------------------------------------------------------
# Telegram summary settings: timezone + summary_time
# ---------------------------------------------------------------------------


async def test_get_me_summary_settings_defaults(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    resp = await client.get(
        "/api/v1/users/me", headers=_auth_header(registered_user["access_token"])
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["timezone"] is None
    assert data["summary_time"] == "10:00"


async def test_update_me_summary_settings_persisted(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    headers = _auth_header(registered_user["access_token"])

    patch_resp = await client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"timezone": "Europe/Berlin", "summary_time": "08:30"},
    )
    get_resp = await client.get("/api/v1/users/me", headers=headers)

    assert patch_resp.status_code == 200
    for data in (patch_resp.json(), get_resp.json()):
        assert data["timezone"] == "Europe/Berlin"
        assert data["summary_time"] == "08:30"


@pytest.mark.parametrize("bad_time", ["8:30", "0830", "08:30:00", "noon", ""])
async def test_update_me_summary_time_bad_format_rejected(
    client: httpx.AsyncClient, registered_user: dict, bad_time: str
) -> None:
    resp = await client.patch(
        "/api/v1/users/me",
        headers=_auth_header(registered_user["access_token"]),
        json={"summary_time": bad_time},
    )

    assert resp.status_code == 422


@pytest.mark.parametrize("bad_time", ["24:00", "25:00", "12:60", "99:99"])
async def test_update_me_summary_time_out_of_range_rejected(
    client: httpx.AsyncClient, registered_user: dict, bad_time: str
) -> None:
    resp = await client.patch(
        "/api/v1/users/me",
        headers=_auth_header(registered_user["access_token"]),
        json={"summary_time": bad_time},
    )

    assert resp.status_code == 422


@pytest.mark.parametrize("good_time", ["00:00", "09:05", "19:59", "23:59"])
async def test_update_me_summary_time_range_edges_accepted(
    client: httpx.AsyncClient, registered_user: dict, good_time: str
) -> None:
    resp = await client.patch(
        "/api/v1/users/me",
        headers=_auth_header(registered_user["access_token"]),
        json={"summary_time": good_time},
    )

    assert resp.status_code == 200
    assert resp.json()["summary_time"] == good_time


@pytest.mark.parametrize(
    "bad_zone", ["Not/AZone", "Mars/Olympus_Mons", "../etc/passwd", "", " "]
)
async def test_update_me_unknown_timezone_rejected(
    client: httpx.AsyncClient, registered_user: dict, bad_zone: str
) -> None:
    resp = await client.patch(
        "/api/v1/users/me",
        headers=_auth_header(registered_user["access_token"]),
        json={"timezone": bad_zone},
    )

    assert resp.status_code == 422


@pytest.mark.parametrize("zone", ["UTC", "America/New_York", "Asia/Kolkata", None])
async def test_update_me_valid_timezone_accepted(
    client: httpx.AsyncClient, registered_user: dict, zone: str | None
) -> None:
    resp = await client.patch(
        "/api/v1/users/me",
        headers=_auth_header(registered_user["access_token"]),
        json={"timezone": zone},
    )

    assert resp.status_code == 200
    assert resp.json()["timezone"] == zone


async def test_update_me_timezone_too_long_rejected(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    resp = await client.patch(
        "/api/v1/users/me",
        headers=_auth_header(registered_user["access_token"]),
        json={"timezone": "A" * 65},
    )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /users/me/change-password
# ---------------------------------------------------------------------------


async def test_change_password_success(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    resp = await client.post(
        "/api/v1/users/me/change-password",
        headers=_auth_header(token),
        json={
            "current_password": "securepassword123",
            "new_password": "evenmoresecure456",
        },
    )
    assert resp.status_code == 200

    # Verify login works with the new password
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "testuser@example.com", "password": "evenmoresecure456"},
    )
    assert login_resp.status_code == 200


async def test_change_password_wrong_current(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    resp = await client.post(
        "/api/v1/users/me/change-password",
        headers=_auth_header(token),
        json={
            "current_password": "totallyWrong",
            "new_password": "doesntmatter123",
        },
    )
    assert resp.status_code == 400
