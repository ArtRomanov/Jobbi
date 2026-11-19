from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import summary as summary_handler
from app.bot.handlers.dialog import NOT_LINKED_MESSAGE
from app.models.telegram_link import TelegramLink
from app.models.user import User
from app.services.summary_service import EMPTY_STATE_MESSAGE
from tests.conftest import TestSessionLocal

CHAT_ID = 555_000_111

type MakeUser = Callable[..., Awaitable[User]]


@pytest.fixture(autouse=True)
def _use_test_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the handler's session factory at the in-memory test DB."""
    monkeypatch.setattr(summary_handler, "async_session", TestSessionLocal)


def _fake_update_and_context(
    chat_id: int | None,
) -> tuple[SimpleNamespace, SimpleNamespace]:
    chat = SimpleNamespace(id=chat_id) if chat_id is not None else None
    update = SimpleNamespace(effective_chat=chat)
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    return update, context


async def test_summary_for_linked_chat_sends_summary(
    db_session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    db_session.add(TelegramLink(user_id=user.id, chat_id=CHAT_ID))
    await db_session.commit()
    update, context = _fake_update_and_context(CHAT_ID)

    await summary_handler.handle_summary(update, context)

    context.bot.send_message.assert_awaited_once()
    kwargs = context.bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == CHAT_ID
    assert kwargs["text"].startswith(EMPTY_STATE_MESSAGE)


async def test_summary_for_unlinked_chat_sends_not_linked(
    db_session: AsyncSession,
) -> None:
    update, context = _fake_update_and_context(CHAT_ID)

    await summary_handler.handle_summary(update, context)

    context.bot.send_message.assert_awaited_once_with(
        chat_id=CHAT_ID, text=NOT_LINKED_MESSAGE
    )


async def test_summary_without_chat_is_noop() -> None:
    update, context = _fake_update_and_context(None)

    await summary_handler.handle_summary(update, context)

    context.bot.send_message.assert_not_awaited()
