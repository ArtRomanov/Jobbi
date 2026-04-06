from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.claude_client import build_system_prompt

BASE_URL = "/api/v1/applications"


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


def _chat_url(app_id: str) -> str:
    return f"{BASE_URL}/{app_id}/chat"


# ---------------------------------------------------------------------------
# Chat History CRUD
# ---------------------------------------------------------------------------


async def _send_message_mocked(
    client: httpx.AsyncClient,
    app_id: str,
    token: str,
    content: str = "Hello",
) -> httpx.Response:
    """Send a chat message with the Claude streaming response mocked out."""

    async def _fake_stream(*args, **kwargs):
        yield "fake response"

    with patch(
        "app.services.chat_service.stream_claude_response",
        side_effect=_fake_stream,
    ):
        return await client.post(
            _chat_url(app_id),
            json={"content": content},
            headers=_auth_header(token),
        )


async def test_get_empty_history(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    app_data = await _create_app(client, token)
    app_id = app_data["id"]

    resp = await client.get(_chat_url(app_id), headers=_auth_header(token))
    assert resp.status_code == 200
    assert resp.json() == []


async def test_send_message_persists_user_message(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    app_data = await _create_app(client, token)
    app_id = app_data["id"]

    resp = await _send_message_mocked(client, app_id, token, "Hi there")
    assert resp.status_code == 200

    # Verify user message (and assistant reply) appear in history
    resp = await client.get(_chat_url(app_id), headers=_auth_header(token))
    assert resp.status_code == 200
    messages = resp.json()
    assert len(messages) >= 1

    user_messages = [m for m in messages if m["role"] == "user"]
    assert len(user_messages) == 1
    assert user_messages[0]["content"] == "Hi there"


async def test_clear_history(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    app_data = await _create_app(client, token)
    app_id = app_data["id"]

    # Send a message
    await _send_message_mocked(client, app_id, token, "Some message")

    # Clear history
    resp = await client.delete(_chat_url(app_id), headers=_auth_header(token))
    assert resp.status_code == 200
    assert resp.json()["message"] == "Chat history cleared."

    # History should be empty
    resp = await client.get(_chat_url(app_id), headers=_auth_header(token))
    assert resp.status_code == 200
    assert resp.json() == []


async def test_history_ordered_by_created_at(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    app_data = await _create_app(client, token)
    app_id = app_data["id"]

    # Send multiple messages
    await _send_message_mocked(client, app_id, token, "First")
    await _send_message_mocked(client, app_id, token, "Second")

    resp = await client.get(_chat_url(app_id), headers=_auth_header(token))
    assert resp.status_code == 200
    messages = resp.json()

    # Extract user messages only (assistant messages interleave)
    user_messages = [m for m in messages if m["role"] == "user"]
    assert len(user_messages) == 2
    assert user_messages[0]["content"] == "First"
    assert user_messages[1]["content"] == "Second"

    # Verify overall ordering by created_at
    timestamps = [m["created_at"] for m in messages]
    assert timestamps == sorted(timestamps)


# ---------------------------------------------------------------------------
# System Prompt Construction
# ---------------------------------------------------------------------------


class _FakeApplication:
    """Minimal stand-in for Application model attributes used by build_system_prompt."""

    def __init__(
        self,
        company_name: str = "TestCo",
        role_title: str = "Engineer",
        job_url: str | None = None,
        status: str = "researching",
        notes: str | None = None,
        cv_id: str | None = None,
    ):
        self.company_name = company_name
        self.role_title = role_title
        self.job_url = job_url
        self.status = status
        self.notes = notes
        self.cv_id = cv_id


class _FakeCv:
    """Minimal stand-in for Cv model attributes used by build_system_prompt."""

    def __init__(
        self,
        name: str = "My CV",
        personal_info: dict | None = None,
        summary: str | None = None,
        work_experience: list | None = None,
        education: list | None = None,
        skills: str | None = None,
        languages: str | None = None,
    ):
        self.name = name
        self.personal_info = personal_info
        self.summary = summary
        self.work_experience = work_experience
        self.education = education
        self.skills = skills
        self.languages = languages


def test_build_system_prompt_without_cv() -> None:
    app = _FakeApplication(company_name="Acme Inc", role_title="Senior Dev")
    prompt = build_system_prompt(app, None)

    assert "Acme Inc" in prompt
    assert "Senior Dev" in prompt
    # No CV section header
    assert "Candidate's CV" not in prompt


def test_build_system_prompt_with_cv() -> None:
    app = _FakeApplication(company_name="MegaCorp", role_title="SRE")
    cv = _FakeCv(
        name="Main CV",
        personal_info={"full_name": "Jane Doe"},
        summary="Experienced SRE with 5 years of production ops.",
        work_experience=[
            {
                "role": "SRE",
                "company": "CloudCo",
                "start_date": "2020-01",
                "end_date": "2023-06",
                "description": "Managed infra",
            }
        ],
        education=[
            {
                "degree": "BSc",
                "field_of_study": "CS",
                "institution": "MIT",
                "start_year": "2016",
                "end_year": "2020",
            }
        ],
        skills="Python, Kubernetes, Terraform",
        languages="English, German",
    )
    prompt = build_system_prompt(app, cv)

    assert "MegaCorp" in prompt
    assert "SRE" in prompt
    assert "Main CV" in prompt
    assert "Jane Doe" in prompt
    assert "Experienced SRE" in prompt
    assert "CloudCo" in prompt
    assert "BSc" in prompt
    assert "Python, Kubernetes, Terraform" in prompt
    assert "English, German" in prompt


def test_build_system_prompt_with_notes() -> None:
    app = _FakeApplication(
        company_name="NotesCo",
        role_title="Dev",
        notes="Referred by Alice",
    )
    prompt = build_system_prompt(app, None)

    assert "Referred by Alice" in prompt
    assert "Notes" in prompt


def test_build_system_prompt_with_job_url() -> None:
    app = _FakeApplication(
        company_name="UrlCo",
        role_title="Dev",
        job_url="https://example.com/job/42",
    )
    prompt = build_system_prompt(app, None)

    assert "https://example.com/job/42" in prompt
    assert "Job URL" in prompt


# ---------------------------------------------------------------------------
# Streaming Endpoint (mock Anthropic)
# ---------------------------------------------------------------------------


async def test_stream_returns_sse_format(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token = registered_user["access_token"]
    app_data = await _create_app(client, token)
    app_id = app_data["id"]

    async def _fake_stream(*args, **kwargs):
        yield "Hello "
        yield "world"

    with patch(
        "app.services.chat_service.stream_claude_response",
        side_effect=_fake_stream,
    ):
        resp = await client.post(
            _chat_url(app_id),
            json={"content": "Test question"},
            headers=_auth_header(token),
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    body = resp.text
    # Must contain token events with our test chunks
    assert "event: token" in body
    assert '"Hello "' in body or "Hello " in body
    assert "world" in body
    # Must end with a done event
    assert "event: done" in body


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


async def test_cannot_access_other_users_chat(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    token_a = registered_user["access_token"]
    app_data = await _create_app(client, token_a)
    app_id = app_data["id"]

    # Register a second user
    user_b = await _register_user(client, email="userb@example.com")
    token_b = user_b["access_token"]

    # User B tries to GET User A's chat history
    resp = await client.get(_chat_url(app_id), headers=_auth_header(token_b))
    assert resp.status_code == 404
