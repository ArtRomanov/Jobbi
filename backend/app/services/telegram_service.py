import secrets
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy import ColumnElement, and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telegram_connection_code import TelegramConnectionCode
from app.models.telegram_link import TelegramLink

CODE_EXPIRY_MINUTES = 10
CODE_LENGTH = 6
CODE_ALPHABET = string.ascii_uppercase + string.digits
MAX_CODE_GENERATION_ATTEMPTS = 10


class CodeGenerationError(RuntimeError):
    """Could not find a code value that is not already active."""


def _generate_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _is_active(now: datetime) -> ColumnElement[bool]:
    """Filter for codes that can still be redeemed (unused and unexpired)."""
    return and_(
        TelegramConnectionCode.used_at.is_(None),
        TelegramConnectionCode.expires_at >= now,
    )


async def _generate_unique_active_code(db: AsyncSession, now: datetime) -> str:
    """Return a code value that no other active code currently holds.

    Used/expired rows may share the value; they can never be redeemed again.

    Raises:
        CodeGenerationError: if every attempt collided (practically impossible
            with 36^6 values, but bounded so a bug can't loop forever).
    """
    for _ in range(MAX_CODE_GENERATION_ATTEMPTS):
        candidate = _generate_code()
        clash = await db.execute(
            select(TelegramConnectionCode.id)
            .where(TelegramConnectionCode.code == candidate, _is_active(now))
            .limit(1)
        )
        if clash.first() is None:
            return candidate
    raise CodeGenerationError("Could not generate a unique connection code.")


async def create_connection_code(
    db: AsyncSession, user_id: str
) -> TelegramConnectionCode:
    """Generate a new code for the user, invalidating any prior active codes.

    Raises:
        CodeGenerationError: if no non-colliding code could be generated.
    """
    # Invalidate prior unused codes for this user
    await db.execute(
        delete(TelegramConnectionCode).where(
            TelegramConnectionCode.user_id == user_id,
            TelegramConnectionCode.used_at.is_(None),
        )
    )

    now = _now_naive()
    code = TelegramConnectionCode(
        user_id=user_id,
        code=await _generate_unique_active_code(db, now),
        expires_at=now + timedelta(minutes=CODE_EXPIRY_MINUTES),
    )
    db.add(code)
    await db.commit()
    await db.refresh(code)
    return code


async def verify_and_consume_code(
    db: AsyncSession, code: str, chat_id: int, telegram_username: str | None
) -> TelegramLink | None:
    """Verify a code and create a link. Returns None if invalid/expired/used.

    If the user already has a link, it is replaced.
    If the chat_id is already linked to a different user, returns None.
    If more than one active code shares the value (only possible through a
    concurrent-generation race), returns None rather than guess which user
    the code belongs to.
    """
    now = _now_naive()
    result = await db.execute(
        select(TelegramConnectionCode)
        .where(TelegramConnectionCode.code == code, _is_active(now))
        .limit(2)
    )
    matches = result.scalars().all()
    if len(matches) != 1:
        return None
    record = matches[0]

    # Check if chat_id already linked to a different user
    existing_chat = await db.execute(
        select(TelegramLink).where(TelegramLink.chat_id == chat_id)
    )
    existing = existing_chat.scalar_one_or_none()
    if existing is not None and existing.user_id != record.user_id:
        return None

    # Remove any existing link for this user
    await db.execute(
        delete(TelegramLink).where(TelegramLink.user_id == record.user_id)
    )

    link = TelegramLink(
        user_id=record.user_id,
        chat_id=chat_id,
        telegram_username=telegram_username,
    )
    db.add(link)
    record.used_at = now

    await db.commit()
    await db.refresh(link)
    return link


async def get_user_link(
    db: AsyncSession, user_id: str
) -> TelegramLink | None:
    result = await db.execute(
        select(TelegramLink).where(TelegramLink.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_link_by_chat(
    db: AsyncSession, chat_id: int
) -> TelegramLink | None:
    result = await db.execute(
        select(TelegramLink).where(TelegramLink.chat_id == chat_id)
    )
    return result.scalar_one_or_none()


async def delete_user_link(db: AsyncSession, user_id: str) -> bool:
    link = await get_user_link(db, user_id)
    if link is None:
        return False
    await db.delete(link)
    await db.commit()
    return True
