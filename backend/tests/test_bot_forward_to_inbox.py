"""Channel posts forwarded to the bot land in the Inbox; other text keeps the
tracker dialog."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TypeAlias
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import (
    Chat,
    Message,
    MessageEntity,
    MessageOriginChannel,
    MessageOriginUser,
    Update,
)
from telegram import User as TgUser
from telegram.ext import ApplicationBuilder

from app.bot.__main__ import add_handlers
from app.bot.handlers import dialog, inbox_forward, start
from app.bot.handlers.inbox_forward import (
    ADDED_MESSAGE,
    ADDED_NO_DESCRIPTION_MESSAGE,
    ALREADY_SEEN_MESSAGE,
    NO_TEXT_MESSAGE,
    build_forwarded_post,
)
from app.discovery.fetchers.telegram import MAX_TEXT_CHARS
from app.discovery.types import PostLink
from app.models.telegram_conversation import TelegramConversation
from app.models.telegram_link import TelegramLink
from app.models.user import User
from app.models.vacancy import Vacancy, VacancyCardSource
from app.models.vacancy_search_settings import VacancySearchSettings
from tests.conftest import TestSessionLocal

CHAT_ID = 424_242
PRIVATE_CHANNEL_ID = -1001234567890
POSTED = datetime(2026, 11, 20, 9, 30, tzinfo=UTC)

MakeUser: TypeAlias = Callable[..., Awaitable[User]]


@pytest.fixture(autouse=True)
def _use_test_db(monkeypatch: pytest.MonkeyPatch) -> None:
    for module in (start, dialog, inbox_forward):
        monkeypatch.setattr(module, "async_session", TestSessionLocal)


def _channel_origin(
    *, username: str | None = None, title: str | None = "Secret Jobs", post_id: int = 42
) -> MessageOriginChannel:
    return MessageOriginChannel(
        date=POSTED,
        chat=Chat(
            id=PRIVATE_CHANNEL_ID, type=Chat.CHANNEL, title=title, username=username
        ),
        message_id=post_id,
    )


def _message(
    *,
    text: str | None = "Senior React dev, remote",
    caption: str | None = None,
    entities: list[MessageEntity] | None = None,
    caption_entities: list[MessageEntity] | None = None,
    origin: object | None = None,
) -> Message:
    return Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=CHAT_ID, type=Chat.PRIVATE),
        from_user=TgUser(id=7, first_name="Ann", is_bot=False),
        text=text,
        caption=caption,
        entities=entities,
        caption_entities=caption_entities,
        forward_origin=origin,
    )


def _update(message: Message) -> Update:
    return Update(update_id=1, message=message)


def _context() -> SimpleNamespace:
    return SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))


def _replies(context: SimpleNamespace) -> list[str]:
    return [call.kwargs["text"] for call in context.bot.send_message.call_args_list]


@pytest.fixture
async def linked_user(db_session: AsyncSession, make_user: MakeUser) -> str:
    user = await make_user()
    db_session.add(TelegramLink(user_id=user.id, chat_id=CHAT_ID))
    await db_session.commit()
    return user.id


async def _set_description(db: AsyncSession, user_id: str, text: str) -> None:
    db.add(VacancySearchSettings(user_id=user_id, description=text, exclude_terms=[]))
    await db.commit()


async def _cards(db: AsyncSession) -> list[Vacancy]:
    db.expire_all()
    return list((await db.scalars(select(Vacancy))).all())


# --- building the post -------------------------------------------------------------


def test_private_channel_post_uses_internal_id() -> None:
    channel, post = build_forwarded_post(_message(), _channel_origin())

    assert channel.handle == "c1234567890"
    assert channel.label == "Secret Jobs"
    assert post.external_key == "tgc:1234567890/42"
    assert post.url == "https://t.me/c/1234567890/42"
    assert post.posted_at == datetime(2026, 11, 20, 9, 30)
    assert post.text == "Senior React dev, remote"


def test_public_channel_post_matches_fetcher_key() -> None:
    channel, post = build_forwarded_post(
        _message(), _channel_origin(username="React_Jobs")
    )

    assert channel.handle == "react_jobs"
    assert post.external_key == "tg:react_jobs/42"
    assert post.url == "https://t.me/react_jobs/42"


def test_caption_is_used_for_media_posts() -> None:
    text = "Apply: https://jobs.example.com/1"
    message = _message(
        text=None,
        caption=text,
        caption_entities=[MessageEntity(MessageEntity.URL, 7, len(text) - 7)],
    )

    _, post = build_forwarded_post(message, _channel_origin())

    assert post.text == text
    assert post.job_link == "https://jobs.example.com/1"


def test_job_link_skips_telegram_links_and_reads_text_links() -> None:
    text = "Channel t.me/other and apply here"
    message = _message(
        text=text,
        entities=[
            MessageEntity(MessageEntity.URL, 8, len("t.me/other")),
            MessageEntity(
                MessageEntity.TEXT_LINK,
                text.index("here"),
                4,
                url="https://jobs.example.com/apply?utm_source=tg",
            ),
        ],
    )

    _, post = build_forwarded_post(message, _channel_origin())

    assert post.job_link == "https://jobs.example.com/apply"


def test_post_without_text_is_not_built() -> None:
    assert build_forwarded_post(_message(text=None), _channel_origin()) is None


# --- the handler -------------------------------------------------------------------


async def test_channel_forward_adds_pending_card(
    db_session: AsyncSession, linked_user: str
) -> None:
    await _set_description(db_session, linked_user, "React, remote")
    context = _context()

    await dialog.handle_message(_update(_message(origin=_channel_origin())), context)

    [card] = await _cards(db_session)
    assert (card.user_id, card.state) == (linked_user, "pending")
    [source] = (await db_session.scalars(select(VacancyCardSource))).all()
    assert (source.source_kind, source.label) == ("tg_forward", "Secret Jobs")
    assert _replies(context) == [ADDED_MESSAGE]
    conversation = await db_session.scalar(select(TelegramConversation))
    assert conversation is None  # no tracker dialog started


async def test_channel_forward_without_description_says_how_to_rate(
    db_session: AsyncSession, linked_user: str
) -> None:
    context = _context()

    await dialog.handle_message(_update(_message(origin=_channel_origin())), context)

    assert _replies(context) == [ADDED_NO_DESCRIPTION_MESSAGE]


async def test_same_post_forwarded_twice(
    db_session: AsyncSession, linked_user: str
) -> None:
    context = _context()
    update = _update(_message(origin=_channel_origin()))

    await dialog.handle_message(update, context)
    await dialog.handle_message(update, context)

    assert len(await _cards(db_session)) == 1
    assert _replies(context)[-1] == ALREADY_SEEN_MESSAGE


async def test_media_only_forward_is_rejected(
    db_session: AsyncSession, linked_user: str
) -> None:
    context = _context()
    message = _message(text=None, caption=None, origin=_channel_origin())

    await dialog.handle_message(_update(message), context)

    assert await _cards(db_session) == []
    assert _replies(context) == [NO_TEXT_MESSAGE]


async def test_unlinked_chat_stores_nothing(db_session: AsyncSession) -> None:
    context = _context()

    await dialog.handle_message(_update(_message(origin=_channel_origin())), context)

    assert await _cards(db_session) == []
    assert _replies(context) == [dialog.NOT_LINKED_MESSAGE]


async def test_forward_from_a_person_keeps_tracker_dialog(
    db_session: AsyncSession, linked_user: str
) -> None:
    origin = MessageOriginUser(
        date=POSTED, sender_user=TgUser(id=9, first_name="Bob", is_bot=False)
    )
    context = _context()

    await dialog.handle_message(_update(_message(origin=origin)), context)

    assert await _cards(db_session) == []
    conversation = await db_session.scalar(select(TelegramConversation))
    assert conversation is not None
    assert conversation.step == dialog.STEP_AWAITING_COMPANY


async def test_captioned_photo_that_is_not_forwarded_is_ignored(
    db_session: AsyncSession, linked_user: str
) -> None:
    context = _context()

    await dialog.handle_message(_update(_message(text=None, caption="hi")), context)

    assert _replies(context) == []
    assert await db_session.scalar(select(TelegramConversation)) is None


def test_message_handler_accepts_forwarded_captions() -> None:
    app = ApplicationBuilder().token("123:fake").build()
    add_handlers(app)
    message = _message(text=None, caption="Job", origin=_channel_origin())

    assert any(
        handler.check_update(_update(message))
        for group in app.handlers.values()
        for handler in group
    )


@pytest.mark.parametrize(
    ("text", "caption", "entities"),
    [
        (None, None, None),  # a photo/video forwarded without a caption
        ("/hiring React devs", None, [MessageEntity(MessageEntity.BOT_COMMAND, 0, 7)]),
        ("/start now", None, [MessageEntity(MessageEntity.BOT_COMMAND, 0, 6)]),
    ],
)
def test_any_channel_forward_reaches_the_inbox_handler(
    text: str | None, caption: str | None, entities: list[MessageEntity] | None
) -> None:
    app = ApplicationBuilder().token("123:fake").build()
    add_handlers(app)
    update = _update(
        _message(
            text=text, caption=caption, entities=entities, origin=_channel_origin()
        )
    )

    # The first handler that takes the update is the one that runs.
    first = next(h for h in app.handlers[0] if h.check_update(update))

    assert first.callback is dialog.handle_message


def test_overlong_job_link_is_dropped() -> None:
    url = "https://jobs.example.com/" + "a" * 2100
    message = _message(
        text=url, entities=[MessageEntity(MessageEntity.URL, 0, len(url))]
    )

    _, post = build_forwarded_post(message, _channel_origin())

    assert post.job_link is None


# --- links per line ----------------------------------------------------------------


def _utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _url_entity(text: str, url: str) -> MessageEntity:
    """A URL entity over `url` in `text`, with Telegram's UTF-16 offsets."""
    start = text.index(url)
    return MessageEntity(MessageEntity.URL, _utf16_len(text[:start]), _utf16_len(url))


def _text_link(text: str, label: str, url: str) -> MessageEntity:
    start = text.index(label)
    return MessageEntity(
        MessageEntity.TEXT_LINK,
        _utf16_len(text[:start]),
        _utf16_len(label),
        url=url,
    )


LINKS_TEXT = (
    "\n  🔥🔥 Two roles\n"
    "🚀 Frontend: https://jobs.example.com/fe?utm_source=tg\n"
    "Chat t.me/acme_chat\n"
    "👩‍💻 Backend: apply here"
)
LINKS_ENTITIES = [
    _url_entity(LINKS_TEXT, "https://jobs.example.com/fe?utm_source=tg"),
    _url_entity(LINKS_TEXT, "t.me/acme_chat"),
    _text_link(LINKS_TEXT, "apply here", "https://jobs.example.com/be/"),
]
LINKS_EXPECTED = (
    PostLink(line=2, url="https://jobs.example.com/fe"),
    PostLink(line=4, url="https://jobs.example.com/be"),
)


def test_links_carry_lines_of_the_stored_text() -> None:
    message = _message(text=LINKS_TEXT, entities=LINKS_ENTITIES)

    _, post = build_forwarded_post(message, _channel_origin())

    # The stored text is stripped, so the leading blank line is not counted.
    assert post.text.split("\n")[0] == "🔥🔥 Two roles"
    assert post.links == LINKS_EXPECTED
    assert post.job_link == "https://jobs.example.com/fe"


def test_caption_links_carry_lines() -> None:
    message = _message(text=None, caption=LINKS_TEXT, caption_entities=LINKS_ENTITIES)

    _, post = build_forwarded_post(message, _channel_origin())

    assert post.links == LINKS_EXPECTED


def test_text_link_starting_with_a_line_break_counts_on_its_visible_line() -> None:
    text = "Roles:\n\nDesigner\nEnd"
    entity = MessageEntity(
        MessageEntity.TEXT_LINK,
        text.index("\n"),
        len("\n\nDesigner"),
        url="https://jobs.example.com/design",
    )

    _, post = build_forwarded_post(
        _message(text=text, entities=[entity]), _channel_origin()
    )

    assert post.links == (PostLink(line=3, url="https://jobs.example.com/design"),)


def test_links_beyond_the_text_cap_are_dropped() -> None:
    text = (
        "https://jobs.example.com/kept\n"
        + "x" * MAX_TEXT_CHARS
        + " jobs.example.com/cut"
    )
    message = _message(
        text=text,
        entities=[
            _url_entity(text, "https://jobs.example.com/kept"),
            _url_entity(text, "jobs.example.com/cut"),
        ],
    )

    _, post = build_forwarded_post(message, _channel_origin())

    assert len(post.text) == MAX_TEXT_CHARS
    assert post.links == (PostLink(line=1, url="https://jobs.example.com/kept"),)


def test_overlong_links_are_not_post_links() -> None:
    url = "https://jobs.example.com/" + "a" * 2100
    message = _message(
        text=f"Apply {url}\nor https://ok.example.com",
        entities=[
            MessageEntity(MessageEntity.URL, 6, len(url)),
            MessageEntity(MessageEntity.URL, 6 + len(url) + 4, 22),
        ],
    )

    _, post = build_forwarded_post(message, _channel_origin())

    assert post.links == (PostLink(line=2, url="https://ok.example.com"),)


@pytest.mark.parametrize("field", ["text", "caption"])
def test_emoji_before_a_link_at_line_end_keeps_its_line(field: str) -> None:
    """Emoji take two UTF-16 units: a naive offset would land on the next line."""
    text = "🔥🔥🔥🔥🔥🔥 a.io\nNext line"
    entities = [_url_entity(text, "a.io")]
    message = (
        _message(text=text, entities=entities)
        if field == "text"
        else _message(text=None, caption=text, caption_entities=entities)
    )

    _, post = build_forwarded_post(message, _channel_origin())

    assert post.links == (PostLink(line=1, url="https://a.io"),)
