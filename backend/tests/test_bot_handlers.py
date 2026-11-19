"""Tests for bot entry points: chat-type restriction, code-guess throttling and
status callback validation."""

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import TypeAlias
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Chat, Message, MessageEntity, Update
from telegram import User as TgUser
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
)

from app.bot.__main__ import add_handlers
from app.bot.handlers import dialog, start
from app.bot.handlers.start import (
    INVALID_CODE_MESSAGE,
    LINK_SUCCESS_MESSAGE,
    TOO_MANY_ATTEMPTS_MESSAGE,
    FailedCodeLimiter,
)
from app.models.application import Application as JobApplication
from app.models.telegram_conversation import TelegramConversation
from app.models.telegram_link import TelegramLink
from app.models.user import User
from app.services.telegram_service import create_connection_code
from tests.conftest import TestSessionLocal

FAKE_TOKEN = "123:fake"
CHAT_ID = 424_242
OTHER_CHAT_ID = 535_353

MakeUser: TypeAlias = Callable[..., Awaitable[User]]


@pytest.fixture(autouse=True)
def _use_test_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(start, "async_session", TestSessionLocal)
    monkeypatch.setattr(dialog, "async_session", TestSessionLocal)


# ---------------------------------------------------------------------------
# Private chats only
# ---------------------------------------------------------------------------


def _message_update(chat_type: str, text: str) -> Update:
    entities = (
        [MessageEntity(MessageEntity.BOT_COMMAND, 0, len(text.split()[0]))]
        if text.startswith("/")
        else None
    )
    message = Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=-100 if chat_type != Chat.PRIVATE else CHAT_ID, type=chat_type),
        from_user=TgUser(id=7, first_name="Ann", is_bot=False),
        text=text,
        entities=entities,
    )
    return Update(update_id=1, message=message)


@pytest.fixture
def bot_app() -> Application:
    app = ApplicationBuilder().token(FAKE_TOKEN).build()
    add_handlers(app)
    return app


def _registered_handlers(app: Application) -> list[object]:
    return [h for group in app.handlers.values() for h in group]


def _sample_text(handler: object) -> str:
    if isinstance(handler, CommandHandler):
        return f"/{next(iter(handler.commands))}"
    return "https://jobs.example.com/123 great role"


def test_every_handler_kind_is_covered(bot_app: Application) -> None:
    handlers = _registered_handlers(bot_app)

    assert handlers
    assert all(
        isinstance(h, CommandHandler | MessageHandler | CallbackQueryHandler)
        for h in handlers
    )


@pytest.mark.parametrize("chat_type", [Chat.GROUP, Chat.SUPERGROUP, Chat.CHANNEL])
def test_message_and_command_handlers_ignore_non_private_chats(
    bot_app: Application, chat_type: str
) -> None:
    for handler in _registered_handlers(bot_app):
        if isinstance(handler, CallbackQueryHandler):
            continue
        update = _message_update(chat_type, _sample_text(handler))
        assert not handler.filters.check_update(update), handler


def test_message_and_command_handlers_accept_private_chats(
    bot_app: Application,
) -> None:
    for handler in _registered_handlers(bot_app):
        if isinstance(handler, CallbackQueryHandler):
            continue
        update = _message_update(Chat.PRIVATE, _sample_text(handler))
        assert handler.filters.check_update(update), handler


# ---------------------------------------------------------------------------
# Status callback
# ---------------------------------------------------------------------------


def _callback_update(
    data: str, chat_type: str = Chat.PRIVATE, chat_id: int = CHAT_ID
) -> SimpleNamespace:
    query = SimpleNamespace(
        data=data, answer=AsyncMock(), edit_message_text=AsyncMock()
    )
    return SimpleNamespace(
        callback_query=query,
        effective_chat=SimpleNamespace(id=chat_id, type=chat_type),
    )


@pytest.fixture
async def linked_at_status_step(
    db_session: AsyncSession, make_user: MakeUser
) -> str:
    user = await make_user()
    db_session.add_all(
        [
            TelegramLink(user_id=user.id, chat_id=CHAT_ID),
            TelegramConversation(
                chat_id=CHAT_ID,
                step=dialog.STEP_AWAITING_STATUS,
                context_data={
                    "notes": "posting",
                    "job_url": None,
                    "company_name": "Acme",
                    "role_title": "Engineer",
                },
            ),
        ]
    )
    await db_session.commit()
    return user.id


async def _applications(db: AsyncSession) -> list[JobApplication]:
    return list((await db.execute(select(JobApplication))).scalars().all())


async def _conversation_exists(db: AsyncSession) -> bool:
    result = await db.execute(
        select(TelegramConversation).where(TelegramConversation.chat_id == CHAT_ID)
    )
    return result.scalar_one_or_none() is not None


async def test_status_callback_creates_application(
    db_session: AsyncSession, linked_at_status_step: str
) -> None:
    update = _callback_update("status:applied")

    await dialog.handle_status_callback(update, SimpleNamespace())

    apps = await _applications(db_session)
    assert [(a.user_id, a.status) for a in apps] == [(linked_at_status_step, "applied")]
    update.callback_query.edit_message_text.assert_awaited_once()


@pytest.mark.parametrize(
    "data", ["status:hired-lol", "status:", "status:APPLIED", "status:applied "]
)
async def test_status_callback_rejects_unknown_status(
    db_session: AsyncSession, linked_at_status_step: str, data: str
) -> None:
    update = _callback_update(data)

    await dialog.handle_status_callback(update, SimpleNamespace())

    assert await _applications(db_session) == []
    update.callback_query.answer.assert_awaited_once_with(
        dialog.UNKNOWN_STATUS_MESSAGE
    )
    assert await _conversation_exists(db_session)  # can still tap a real button


@pytest.mark.parametrize("chat_type", [Chat.GROUP, Chat.SUPERGROUP, Chat.CHANNEL])
async def test_status_callback_ignored_outside_private_chat(
    db_session: AsyncSession, linked_at_status_step: str, chat_type: str
) -> None:
    update = _callback_update("status:applied", chat_type=chat_type)

    await dialog.handle_status_callback(update, SimpleNamespace())

    assert await _applications(db_session) == []
    update.callback_query.answer.assert_awaited_once()
    update.callback_query.edit_message_text.assert_not_awaited()
    assert await _conversation_exists(db_session)


# ---------------------------------------------------------------------------
# Failed code throttling
# ---------------------------------------------------------------------------


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(
        start,
        "code_attempt_limiter",
        FailedCodeLimiter(max_failures=5, window_seconds=15 * 60, clock=fake),
    )
    return fake


def _code_update(chat_id: int = CHAT_ID) -> tuple[SimpleNamespace, SimpleNamespace]:
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id, type=Chat.PRIVATE),
        effective_user=SimpleNamespace(username="ann"),
    )
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    return update, context


def _replies(context: SimpleNamespace) -> list[str]:
    return [c.kwargs["text"] for c in context.bot.send_message.await_args_list]


async def _guess(code: str, chat_id: int = CHAT_ID) -> list[str]:
    update, context = _code_update(chat_id)
    assert await start.handle_code_verification(update, context, code) is True
    return _replies(context)


async def test_failed_codes_are_throttled_per_chat(clock: FakeClock) -> None:
    replies = [await _guess("ZZZZZ1") for _ in range(5)]
    assert replies == [[INVALID_CODE_MESSAGE]] * 5

    assert await _guess("ZZZZZ2") == [TOO_MANY_ATTEMPTS_MESSAGE]
    for _ in range(10):
        assert await _guess("ZZZZZ3") == []

    # Other chats are unaffected.
    assert await _guess("ZZZZZ4", chat_id=OTHER_CHAT_ID) == [INVALID_CODE_MESSAGE]


async def test_blocked_chat_cannot_redeem_even_a_valid_code(
    clock: FakeClock, db_session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    code = (await create_connection_code(db_session, user.id)).code
    for _ in range(5):
        await _guess("ZZZZZ1")

    assert await _guess(code) == [TOO_MANY_ATTEMPTS_MESSAGE]
    link = await db_session.execute(
        select(TelegramLink).where(TelegramLink.chat_id == CHAT_ID)
    )
    assert link.scalar_one_or_none() is None


async def test_throttle_lifts_after_window(
    clock: FakeClock, db_session: AsyncSession, make_user: MakeUser
) -> None:
    for _ in range(6):
        await _guess("ZZZZZ1")
    user = await make_user()
    code = (await create_connection_code(db_session, user.id)).code

    clock.now += 15 * 60 + 1

    assert await _guess(code) == [LINK_SUCCESS_MESSAGE]


async def test_successful_link_resets_failures(
    clock: FakeClock, db_session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    code = (await create_connection_code(db_session, user.id)).code
    for _ in range(4):
        await _guess("ZZZZZ1")

    assert await _guess(code) == [LINK_SUCCESS_MESSAGE]
    assert start.code_attempt_limiter.failures(CHAT_ID) == 0


async def test_non_code_text_is_not_counted(clock: FakeClock) -> None:
    update, context = _code_update()
    for _ in range(10):
        assert (
            await start.handle_code_verification(update, context, "hello there")
            is False
        )

    assert start.code_attempt_limiter.failures(CHAT_ID) == 0
