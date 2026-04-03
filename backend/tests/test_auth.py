import hashlib
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.password_reset import PasswordResetToken
from app.services.password_reset_service import create_password_reset, generate_reset_token
from app.models.user import User


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


async def test_register_success(client: httpx.AsyncClient) -> None:
    payload = {
        "email": "new@example.com",
        "password": "validpass123",
        "full_name": "New User",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "new@example.com"
    assert data["user"]["full_name"] == "New User"


async def test_register_duplicate_email(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    payload = {
        "email": "testuser@example.com",  # same as registered_user
        "password": "anotherpassword123",
        "full_name": "Duplicate User",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409


async def test_register_invalid_email(client: httpx.AsyncClient) -> None:
    payload = {
        "email": "not-an-email",
        "password": "validpass123",
        "full_name": "Bad Email",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 422


async def test_register_password_too_short(client: httpx.AsyncClient) -> None:
    payload = {
        "email": "short@example.com",
        "password": "short",
        "full_name": "Short Pass",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


async def test_login_success(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "testuser@example.com", "password": "securepassword123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "testuser@example.com"


async def test_login_wrong_password(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "testuser@example.com", "password": "wrongpassword"},
    )
    assert resp.status_code == 401


async def test_login_nonexistent_email(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "whatever123"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Forgot password
# ---------------------------------------------------------------------------


async def test_forgot_password_existing_email(
    client: httpx.AsyncClient, registered_user: dict
) -> None:
    resp = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "testuser@example.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data


async def test_forgot_password_nonexistent_email(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "nobody@example.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Same generic message — no information leakage
    assert "message" in data


# ---------------------------------------------------------------------------
# Reset password
# ---------------------------------------------------------------------------


async def test_reset_password_success(
    client: httpx.AsyncClient, registered_user: dict, db_session: AsyncSession
) -> None:
    # Look up the user in the DB
    result = await db_session.execute(
        select(User).where(User.email == "testuser@example.com")
    )
    user = result.scalar_one()

    # Create a reset token via the service
    raw_token = await create_password_reset(db_session, user)

    # Reset the password
    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "brandnewpass123"},
    )
    assert resp.status_code == 200

    # Verify login works with the new password
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "testuser@example.com", "password": "brandnewpass123"},
    )
    assert login_resp.status_code == 200


async def test_reset_password_expired_token(
    client: httpx.AsyncClient, registered_user: dict, db_session: AsyncSession
) -> None:
    # Look up the user
    result = await db_session.execute(
        select(User).where(User.email == "testuser@example.com")
    )
    user = result.scalar_one()

    # Create an expired token directly in the DB
    raw_token, token_hash = generate_reset_token()
    expired_reset = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    db_session.add(expired_reset)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "newpassword123"},
    )
    assert resp.status_code == 400


async def test_reset_password_reused_token(
    client: httpx.AsyncClient, registered_user: dict, db_session: AsyncSession
) -> None:
    # Look up the user
    result = await db_session.execute(
        select(User).where(User.email == "testuser@example.com")
    )
    user = result.scalar_one()

    raw_token = await create_password_reset(db_session, user)

    # Use the token once
    resp1 = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "firstnewpass123"},
    )
    assert resp1.status_code == 200

    # Try to use the same token again
    resp2 = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "secondnewpass123"},
    )
    assert resp2.status_code == 400


async def test_reset_password_invalid_token(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": "completely-bogus-token", "new_password": "newpassword123"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


async def test_logout(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Logged out."
