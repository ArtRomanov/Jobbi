import httpx

from app.core.constants import ApplicationStatus

APPS_URL = "/api/v1/applications"
METRICS_URL = "/api/v1/metrics"

RESEARCHING = ApplicationStatus.RESEARCHING.value
APPLIED = ApplicationStatus.APPLIED.value
INTERVIEW = ApplicationStatus.INTERVIEW.value
OFFER = ApplicationStatus.OFFER.value
REJECTED = ApplicationStatus.REJECTED.value
WITHDRAWN = ApplicationStatus.WITHDRAWN.value

ALL_STATUSES = [RESEARCHING, APPLIED, INTERVIEW, OFFER, REJECTED, WITHDRAWN]


def _auth(token: str) -> dict[str, str]:
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
    resp = await client.post(APPS_URL, json=payload, headers=_auth(token))
    assert resp.status_code == 201
    return resp.json()


async def _patch_status(
    client: httpx.AsyncClient, token: str, app_id: str, status: str
) -> None:
    resp = await client.patch(
        f"{APPS_URL}/{app_id}", json={"status": status}, headers=_auth(token)
    )
    assert resp.status_code == 200


async def _get_metrics(
    client: httpx.AsyncClient, token: str, **params: object
) -> dict:
    resp = await client.get(METRICS_URL, params=params, headers=_auth(token))
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# KPI calculation
# ---------------------------------------------------------------------------


async def test_empty_metrics(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    data = await _get_metrics(client, token)

    assert data["kpis"]["total_applications"] == 0
    assert data["kpis"]["active"] == 0
    assert data["kpis"]["response_rate"] == 0.0
    assert data["kpis"]["interviews"] == 0

    assert len(data["pipeline"]) == 6
    for entry in data["pipeline"]:
        assert entry["count"] == 0

    assert len(data["trend"]["points"]) > 0
    for pt in data["trend"]["points"]:
        assert pt["count"] == 0


async def test_total_applications_count(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    for i in range(3):
        await _create_app(client, token, company_name=f"C{i}")

    data = await _get_metrics(client, token)
    assert data["kpis"]["total_applications"] == 3


async def test_active_count_excludes_rejected_and_withdrawn(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    await _create_app(client, token, company_name="A", status=APPLIED)
    await _create_app(client, token, company_name="B", status=INTERVIEW)
    await _create_app(client, token, company_name="C", status=REJECTED)
    await _create_app(client, token, company_name="D", status=WITHDRAWN)

    data = await _get_metrics(client, token)
    assert data["kpis"]["total_applications"] == 4
    assert data["kpis"]["active"] == 2


async def test_interviews_count(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    created = await _create_app(client, token)
    await _patch_status(client, token, created["id"], INTERVIEW)

    data = await _get_metrics(client, token)
    assert data["kpis"]["interviews"] == 1


async def test_interviews_counts_apps_that_passed_through_interview(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    created = await _create_app(client, token)
    await _patch_status(client, token, created["id"], INTERVIEW)
    await _patch_status(client, token, created["id"], OFFER)

    data = await _get_metrics(client, token)
    assert data["kpis"]["interviews"] == 1


# ---------------------------------------------------------------------------
# Response rate
# ---------------------------------------------------------------------------


async def test_response_rate_zero_when_all_in_applied(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    for i in range(3):
        await _create_app(client, token, company_name=f"C{i}", status=APPLIED)

    data = await _get_metrics(client, token)
    assert data["kpis"]["response_rate"] == 0.0


async def test_response_rate_includes_interview_offer_rejected(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    a = await _create_app(client, token, company_name="A")
    b = await _create_app(client, token, company_name="B")
    c = await _create_app(client, token, company_name="C")
    await _patch_status(client, token, a["id"], INTERVIEW)
    await _patch_status(client, token, b["id"], OFFER)
    await _patch_status(client, token, c["id"], REJECTED)

    data = await _get_metrics(client, token)
    assert data["kpis"]["response_rate"] == 1.0


async def test_response_rate_excludes_withdrawn(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    a = await _create_app(client, token, company_name="A")
    await _create_app(client, token, company_name="B", status=APPLIED)
    await _patch_status(client, token, a["id"], WITHDRAWN)

    data = await _get_metrics(client, token)
    assert data["kpis"]["response_rate"] == 0.0


async def test_response_rate_calculation(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    a = await _create_app(client, token, company_name="A")
    for name in ("B", "C", "D"):
        await _create_app(client, token, company_name=name, status=APPLIED)
    await _patch_status(client, token, a["id"], INTERVIEW)

    data = await _get_metrics(client, token)
    assert data["kpis"]["response_rate"] == 0.25


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def test_pipeline_zero_fills_all_six_statuses(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    await _create_app(client, token, status=APPLIED)

    data = await _get_metrics(client, token)
    assert len(data["pipeline"]) == 6
    statuses = {p["status"] for p in data["pipeline"]}
    assert statuses == set(ALL_STATUSES)


async def test_pipeline_counts(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    await _create_app(client, token, company_name="A", status=APPLIED)
    await _create_app(client, token, company_name="B", status=APPLIED)
    await _create_app(client, token, company_name="C", status=INTERVIEW)
    await _create_app(client, token, company_name="D", status=REJECTED)

    data = await _get_metrics(client, token)
    counts = {p["status"]: p["count"] for p in data["pipeline"]}
    assert counts[APPLIED] == 2
    assert counts[INTERVIEW] == 1
    assert counts[REJECTED] == 1
    assert counts[OFFER] == 0
    assert counts[WITHDRAWN] == 0
    assert counts[RESEARCHING] == 0


# ---------------------------------------------------------------------------
# Trend granularity
# ---------------------------------------------------------------------------


async def test_trend_granularity_7d_is_daily(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    data = await _get_metrics(client, token, range="7d")
    assert data["trend"]["granularity"] == "daily"


async def test_trend_granularity_30d_is_daily(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    data = await _get_metrics(client, token, range="30d")
    assert data["trend"]["granularity"] == "daily"


async def test_trend_granularity_90d_is_weekly(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    data = await _get_metrics(client, token, range="90d")
    assert data["trend"]["granularity"] == "weekly"


# ---------------------------------------------------------------------------
# Date range filter
# ---------------------------------------------------------------------------


async def test_default_range_is_30d(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    data = await _get_metrics(client, token)
    assert data["range"] == "30d"


async def test_invalid_range_returns_422(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    resp = await client.get(
        METRICS_URL, params={"range": "invalid"}, headers=_auth(token)
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


async def test_metrics_only_count_user_own_applications(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token_a = registered_user["access_token"]
    await _create_app(client, token_a, company_name="A1")
    await _create_app(client, token_a, company_name="A2")

    user_b = await _register_user(client, email="userb@example.com")
    token_b = user_b["access_token"]
    await _create_app(client, token_b, company_name="B1")

    data_a = await _get_metrics(client, token_a)
    data_b = await _get_metrics(client, token_b)

    assert data_a["kpis"]["total_applications"] == 2
    assert data_b["kpis"]["total_applications"] == 1
