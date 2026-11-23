"""Channel posts forwarded to the bot go to the user's Inbox.

This is how private channels get into Jobbi: the discovery worker can only
read public channels (`t.me/s/<name>`), but a member of a private channel can
forward its posts here. Forwards from people or groups, and typed text, keep
the tracker dialog (`dialog.handle_message`).
"""

from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import select
from telegram import Message, MessageEntity, MessageOriginChannel, Update
from telegram.ext import ContextTypes
from telegram.ext.filters import MessageFilter

from app.core.database import async_session
from app.discovery.fetchers.telegram import MAX_TEXT_CHARS, is_telegram_host
from app.discovery.normalize import normalize_url
from app.discovery.service import (
    ForwardedChannel,
    ForwardOutcome,
    store_forwarded_post,
)
from app.discovery.types import MAX_LINK_CHARS, PostLink, RawPost
from app.models.vacancy_search_settings import VacancySearchSettings

__all__ = [
    "ADDED_MESSAGE",
    "ADDED_NO_DESCRIPTION_MESSAGE",
    "ALREADY_SEEN_MESSAGE",
    "CHANNEL_FORWARD",
    "NO_TEXT_MESSAGE",
    "build_forwarded_post",
    "handle_channel_forward",
]

# Functional spec 012, 2.2. The rating result follows as a reply to the
# forwarded message, sent by the discovery worker (`forward_replies`).
ADDED_MESSAGE = (
    "📥 Got it. Jobbi will rate it and add matching vacancies to your Inbox."
)
ADDED_NO_DESCRIPTION_MESSAGE = (
    "📥 Saved. Describe what you're looking for on the Sources page so Jobbi "
    "can rate it."
)
ALREADY_SEEN_MESSAGE = "Jobbi has already seen this post."
NO_TEXT_MESSAGE = "This post has no text, so there is nothing to add to the Inbox."

# Bot API ids of channels are -100<internal id>; t.me/c/ links use the internal id.
_CHANNEL_ID_OFFSET = 1_000_000_000_000
_LABEL_MAX = 255


class _ChannelForwardFilter(MessageFilter):
    """A message forwarded from a channel (any content, even media only or
    text starting with "/")."""

    def filter(self, message: Message) -> bool:
        return isinstance(message.forward_origin, MessageOriginChannel)


CHANNEL_FORWARD = _ChannelForwardFilter(name="CHANNEL_FORWARD")


def _internal_id(chat_id: int) -> int:
    return (
        -chat_id - _CHANNEL_ID_OFFSET if chat_id < -_CHANNEL_ID_OFFSET else abs(chat_id)
    )


_LINK_TYPES = [MessageEntity.URL, MessageEntity.TEXT_LINK]


def _link_entities(message: Message) -> list[tuple[MessageEntity, str]]:
    """URL and TEXT_LINK entities of the text (or caption) with their text, in
    order."""
    # parse_entities raises on a message without text (a captioned photo).
    entities = (
        message.parse_entities(_LINK_TYPES)
        if message.text is not None
        else message.parse_caption_entities(_LINK_TYPES)
    )
    return sorted(entities.items(), key=lambda item: item[0].offset)


def _entity_url(entity: MessageEntity, text: str) -> str | None:
    """The entity's link normalized if it is http(s) outside Telegram, else None."""
    href = (entity.url if entity.type == MessageEntity.TEXT_LINK else text) or ""
    href = href.strip()
    if entity.type == MessageEntity.URL and "://" not in href:
        href = f"https://{href}"
    try:
        parts = urlsplit(href)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if (
        parts.scheme.lower() in ("http", "https")
        and host
        and not is_telegram_host(host)
    ):
        return normalize_url(href)
    return None


def _first_job_link(entities: list[tuple[MessageEntity, str]]) -> str | None:
    """The first http(s) link outside Telegram, from link entities in order."""
    for entity, text in entities:
        if (link := _entity_url(entity, text)) is not None:
            # Same bound as the column (and the board fetcher).
            return link if len(link) <= MAX_LINK_CHARS else None
    return None


def _post_links(
    entities: list[tuple[MessageEntity, str]], raw: str, stored: str
) -> tuple[PostLink, ...]:
    """Outside links with the line of `stored` (`raw.strip()`, capped) on which
    their visible text starts; links without visible text or beyond the cap are
    dropped."""
    utf16 = raw.encode("utf-16-le")
    lead = len(raw) - len(raw.lstrip())
    links: list[PostLink] = []
    for entity, text in entities:
        url = _entity_url(entity, text)
        if url is None or len(url) > MAX_LINK_CHARS:
            continue
        # Entity offsets count UTF-16 code units; turn them into a str index.
        start = len(utf16[: entity.offset * 2].decode("utf-16-le", errors="replace"))
        visible = next(
            (i for i, char in enumerate(text, start) if not char.isspace()), None
        )
        if visible is None or not 0 <= visible - lead < len(stored):
            continue
        offset = visible - lead
        link = PostLink(line=stored.count("\n", 0, offset) + 1, url=url)
        if link not in links:
            links.append(link)
    return tuple(links)


def build_forwarded_post(
    message: Message, origin: MessageOriginChannel
) -> tuple[ForwardedChannel, RawPost] | None:
    """Card source and post for a forwarded channel post; None without text."""
    raw = message.text or message.caption or ""
    text = raw.strip()[:MAX_TEXT_CHARS]
    if not text:
        return None
    entities = _link_entities(message)
    chat = origin.chat
    username = (chat.username or "").lower()
    post_id = origin.message_id
    if username:
        # Same key and link as the public-channel fetcher, so a channel the
        # user also watches does not produce the post twice.
        handle = username
        external_key = f"tg:{username}/{post_id}"
        url = f"https://t.me/{username}/{post_id}"
    else:
        internal = _internal_id(chat.id)
        handle = f"c{internal}"
        external_key = f"tgc:{internal}/{post_id}"
        url = f"https://t.me/c/{internal}/{post_id}"
    label = (chat.title or (f"@{username}" if username else "Forwarded"))[:_LABEL_MAX]
    posted_at = origin.date.astimezone(UTC).replace(tzinfo=None)
    return (
        ForwardedChannel(handle=handle, label=label),
        RawPost(
            external_key=external_key,
            url=url,
            job_link=_first_job_link(entities),
            title=None,
            company=None,
            text=text,
            posted_at=posted_at,
            links=_post_links(entities, raw, text),
        ),
    )


async def _has_description(user_id: str) -> bool:
    async with async_session() as db:
        description = await db.scalar(
            select(VacancySearchSettings.description).where(
                VacancySearchSettings.user_id == user_id
            )
        )
    return bool((description or "").strip())


async def handle_channel_forward(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: str,
    origin: MessageOriginChannel,
) -> None:
    """Store a forwarded channel post for a linked user and reply."""
    assert update.effective_chat is not None and update.message is not None
    chat_id = update.effective_chat.id
    message_id = update.message.message_id

    built = build_forwarded_post(update.message, origin)
    if built is None:
        await context.bot.send_message(chat_id=chat_id, text=NO_TEXT_MESSAGE)
        return
    channel, post = built
    now = datetime.now(UTC).replace(tzinfo=None)
    outcome = await store_forwarded_post(
        async_session,
        user_id,
        channel,
        post,
        now,
        chat_id=chat_id,
        message_id=message_id,
    )

    if outcome is ForwardOutcome.ADDED:
        reply = (
            ADDED_MESSAGE
            if await _has_description(user_id)
            else ADDED_NO_DESCRIPTION_MESSAGE
        )
    else:
        reply = ALREADY_SEEN_MESSAGE
    await context.bot.send_message(chat_id=chat_id, text=reply)
