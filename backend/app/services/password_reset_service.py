import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.password_reset import PasswordResetToken
from app.models.user import User

logger = structlog.get_logger()

TOKEN_EXPIRY_HOURS = 1


def generate_reset_token() -> tuple[str, str]:
    """Generate a random token and its SHA-256 hash.

    Returns (raw_token, token_hash).
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, token_hash


async def create_password_reset(db: AsyncSession, user: User) -> str:
    """Create a password reset token for the user. Returns the raw token."""
    raw_token, token_hash = generate_reset_token()

    reset = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS),
    )
    db.add(reset)
    await db.commit()

    # Log the reset link to console (no email service in V1)
    reset_link = f"http://localhost:5173/reset-password?token={raw_token}"
    logger.info("Password reset link generated", email=user.email, link=reset_link)

    return raw_token


async def verify_and_use_reset_token(
    db: AsyncSession, raw_token: str, new_password: str
) -> bool:
    """Verify the reset token, update the password, and mark the token as used.

    Returns True on success, False if the token is invalid/expired/used.
    """
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    reset = result.scalar_one_or_none()

    if reset is None:
        return False

    # Check if already used
    if reset.used_at is not None:
        return False

    # Check if expired
    now = datetime.now(timezone.utc)
    expires = reset.expires_at
    # Handle naive datetimes from SQLite
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if now > expires:
        return False

    # Look up the user and update password
    user_result = await db.execute(select(User).where(User.id == reset.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        return False

    user.password_hash = hash_password(new_password)
    reset.used_at = now
    await db.commit()

    return True
