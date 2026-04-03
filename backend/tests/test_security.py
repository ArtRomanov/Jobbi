from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.security import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.core.config import get_settings


def test_hash_password_returns_bcrypt_hash() -> None:
    hashed = hash_password("mypassword")
    # bcrypt hashes start with $2b$
    assert hashed.startswith("$2b$")
    assert len(hashed) == 60


def test_verify_password_correct() -> None:
    hashed = hash_password("mypassword")
    assert verify_password("mypassword", hashed) is True


def test_verify_password_wrong() -> None:
    hashed = hash_password("mypassword")
    assert verify_password("wrongpassword", hashed) is False


def test_create_access_token_returns_string() -> None:
    token = create_access_token(subject="user-123")
    assert isinstance(token, str)
    assert len(token) > 0


def test_decode_access_token_valid() -> None:
    token = create_access_token(subject="user-456")
    subject = decode_access_token(token)
    assert subject == "user-456"


def test_decode_access_token_expired() -> None:
    settings = get_settings()
    # Create a token that expired in the past
    expire = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {"sub": "user-789", "exp": expire}
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)

    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)
    assert exc_info.value.status_code == 401


def test_decode_access_token_invalid_token() -> None:
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token("not-a-valid-jwt")
    assert exc_info.value.status_code == 401
