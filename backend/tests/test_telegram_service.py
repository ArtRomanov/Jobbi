import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telegram_connection_code import TelegramConnectionCode
from app.models.telegram_link import TelegramLink
from app.models.user import User
from app.services import telegram_service
from app.services.telegram_service import (
    create_connection_code,
    delete_user_link,
    get_link_by_chat,
    get_user_link,
    verify_and_consume_code,
)

CODE_PATTERN = re.compile(r"^[A-Z0-9]{6}$")
CHAT_ID = 111_222_333
OTHER_CHAT_ID = 444_555_666

type MakeUser = Callable[..., Awaitable[User]]


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _expire_code(db: AsyncSession, code_id: str) -> None:
    await db.execute(
        update(TelegramConnectionCode)
        .where(TelegramConnectionCode.id == code_id)
        .values(expires_at=_utcnow_naive() - timedelta(seconds=1))
    )
    await db.commit()


# ---------------------------------------------------------------------------
# create_connection_code
# ---------------------------------------------------------------------------


async def test_create_code_format(db_session: AsyncSession, make_user: MakeUser) -> None:
    user = await make_user()

    record = await create_connection_code(db_session, user.id)

    assert CODE_PATTERN.match(record.code)
    assert record.user_id == user.id
    assert record.used_at is None


async def test_create_code_expires_in_ten_minutes(
    db_session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    before = _utcnow_naive()

    record = await create_connection_code(db_session, user.id)

    after = _utcnow_naive()
    assert before + timedelta(minutes=10) <= record.expires_at <= after + timedelta(
        minutes=10
    )


async def test_create_code_invalidates_prior_active_code(
    db_session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    first = await create_connection_code(db_session, user.id)

    second = await create_connection_code(db_session, user.id)

    rows = (
        await db_session.execute(
            select(TelegramConnectionCode).where(
                TelegramConnectionCode.user_id == user.id,
                TelegramConnectionCode.used_at.is_(None),
            )
        )
    ).scalars().all()
    assert [r.id for r in rows] == [second.id]
    assert await verify_and_consume_code(db_session, first.code, CHAT_ID, None) is None


async def test_create_code_does_not_touch_other_users_codes(
    db_session: AsyncSession, make_user: MakeUser
) -> None:
    alice, bob = await make_user(), await make_user()
    alice_code = await create_connection_code(db_session, alice.id)

    await create_connection_code(db_session, bob.id)

    link = await verify_and_consume_code(db_session, alice_code.code, CHAT_ID, None)
    assert link is not None
    assert link.user_id == alice.id


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: codes are not unique across users (no unique constraint, no retry on "
        "collision). Two users holding the same active code make "
        "verify_and_consume_code raise MultipleResultsFound "
        "(telegram_service.py scalar_one_or_none on code lookup)."
    ),
)
async def test_verify_with_colliding_codes_does_not_crash(
    db_session: AsyncSession,
    make_user: MakeUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(telegram_service, "_generate_code", lambda: "ABC123")
    alice, bob = await make_user(), await make_user()
    await create_connection_code(db_session, alice.id)
    await create_connection_code(db_session, bob.id)

    # Must not raise; a sane outcome is either a link or a clean rejection.
    await verify_and_consume_code(db_session, "ABC123", CHAT_ID, None)


# ---------------------------------------------------------------------------
# verify_and_consume_code
# ---------------------------------------------------------------------------


async def test_verify_valid_code_creates_link_and_marks_used(
    db_session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    record = await create_connection_code(db_session, user.id)

    link = await verify_and_consume_code(db_session, record.code, CHAT_ID, "alice_tg")

    assert link is not None
    assert link.user_id == user.id
    assert link.chat_id == CHAT_ID
    assert link.telegram_username == "alice_tg"
    await db_session.refresh(record)
    assert record.used_at is not None


async def test_verify_expired_code_fails(
    db_session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    record = await create_connection_code(db_session, user.id)
    await _expire_code(db_session, record.id)

    link = await verify_and_consume_code(db_session, record.code, CHAT_ID, None)

    assert link is None
    assert await get_user_link(db_session, user.id) is None


async def test_verify_already_used_code_fails(
    db_session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    record = await create_connection_code(db_session, user.id)
    assert await verify_and_consume_code(db_session, record.code, CHAT_ID, None)

    second_attempt = await verify_and_consume_code(
        db_session, record.code, OTHER_CHAT_ID, None
    )

    assert second_attempt is None
    link = await get_user_link(db_session, user.id)
    assert link is not None
    assert link.chat_id == CHAT_ID


@pytest.mark.parametrize("bad_code", ["ZZZZZZ", "", "abc123", "TOOLONGCODE"])
async def test_verify_unknown_code_fails(
    db_session: AsyncSession, make_user: MakeUser, bad_code: str
) -> None:
    user = await make_user()
    await create_connection_code(db_session, user.id)

    assert await verify_and_consume_code(db_session, bad_code, CHAT_ID, None) is None


async def test_verify_chat_already_linked_to_other_user_fails(
    db_session: AsyncSession, make_user: MakeUser
) -> None:
    alice, bob = await make_user(), await make_user()
    alice_code = await create_connection_code(db_session, alice.id)
    await verify_and_consume_code(db_session, alice_code.code, CHAT_ID, None)
    bob_code = await create_connection_code(db_session, bob.id)

    link = await verify_and_consume_code(db_session, bob_code.code, CHAT_ID, None)

    assert link is None
    assert await get_user_link(db_session, bob.id) is None
    alice_link = await get_link_by_chat(db_session, CHAT_ID)
    assert alice_link is not None
    assert alice_link.user_id == alice.id


async def test_verify_relink_replaces_existing_link(
    db_session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    first = await create_connection_code(db_session, user.id)
    await verify_and_consume_code(db_session, first.code, CHAT_ID, "old_name")
    second = await create_connection_code(db_session, user.id)

    link = await verify_and_consume_code(
        db_session, second.code, OTHER_CHAT_ID, "new_name"
    )

    assert link is not None
    links = (
        await db_session.execute(
            select(TelegramLink).where(TelegramLink.user_id == user.id)
        )
    ).scalars().all()
    assert len(links) == 1
    assert links[0].chat_id == OTHER_CHAT_ID
    assert links[0].telegram_username == "new_name"


# ---------------------------------------------------------------------------
# Link lookups / delete
# ---------------------------------------------------------------------------


async def test_get_link_lookups(db_session: AsyncSession, make_user: MakeUser) -> None:
    user = await make_user()
    record = await create_connection_code(db_session, user.id)
    await verify_and_consume_code(db_session, record.code, CHAT_ID, None)

    by_user = await get_user_link(db_session, user.id)
    by_chat = await get_link_by_chat(db_session, CHAT_ID)

    assert by_user is not None
    assert by_chat is not None
    assert by_user.id == by_chat.id


async def test_get_link_returns_none_when_unlinked(
    db_session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()

    assert await get_user_link(db_session, user.id) is None
    assert await get_link_by_chat(db_session, CHAT_ID) is None


async def test_delete_user_link(db_session: AsyncSession, make_user: MakeUser) -> None:
    user = await make_user()
    record = await create_connection_code(db_session, user.id)
    await verify_and_consume_code(db_session, record.code, CHAT_ID, None)

    deleted = await delete_user_link(db_session, user.id)

    assert deleted is True
    assert await get_user_link(db_session, user.id) is None


async def test_delete_user_link_when_none_returns_false(
    db_session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()

    assert await delete_user_link(db_session, user.id) is False
