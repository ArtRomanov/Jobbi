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

from app.core.database import async_session
from app.discovery.fetchers.telegram import MAX_TEXT_CHARS, is_telegram_host
from app.discovery.normalize import normalize_url
from app.discovery.service import (
    ForwardedChannel,
    ForwardOutcome,
    store_forwarded_post,
)
from app.discovery.types import RawPost
from app.models.vacancy_search_settings import VacancySearchSettings

__all__ = [
    "ADDED_MESSAGE",
    "ADDED_NO_DESCRIPTION_MESSAGE",
    "ALREADY_SEEN_MESSAGE",
    "MERGED_MESSAGE",
    "NO_TEXT_MESSAGE",
    "build_forwarded_post",
    "handle_channel_forward",
]

ADDED_MESSAGE = "📥 Added to your Inbox. Jobbi will rate the fit in a minute or two."
ADDED_NO_DESCRIPTION_MESSAGE = (
    "📥 Saved. Describe what you're looking for on the Sources page so Jobbi "
    "can rate it; it shows up in your Inbox once rated."
)
MERGED_MESSAGE = (
    "This job is already in your Inbox. I added this channel to its sources."
)
ALREADY_SEEN_MESSAGE = "Jobbi has already seen this post."
NO_TEXT_MESSAGE = "This post has no text, so there is nothing to add to the Inbox."

# Bot API ids of channels are -100<internal id>; t.me/c/ links use the internal id.
_CHANNEL_ID_OFFSET = 1_000_000_000_000
_LABEL_MAX = 255


def _internal_id(chat_id: int) -> int:
    return (
        -chat_id - _CHANNEL_ID_OFFSET if chat_id < -_CHANNEL_ID_OFFSET else abs(chat_id)
    )


def _first_job_link(message: Message) -> str | None:
    """The first http(s) link outside Telegram, from link entities in order."""
    types = [MessageEntity.URL, MessageEntity.TEXT_LINK]
    # parse_entities raises on a message without text (a captioned photo).
    entities = (
        message.parse_entities(types)
        if message.text is not None
        else message.parse_caption_entities(types)
    )
    for entity, text in sorted(entities.items(), key=lambda item: item[0].offset):
        href = (entity.url if entity.type == MessageEntity.TEXT_LINK else text) or ""
        href = href.strip()
        if entity.type == MessageEntity.URL and "://" not in href:
            href = f"https://{href}"
        try:
            parts = urlsplit(href)
        except ValueError:
            continue
        host = (parts.hostname or "").lower()
        if (
            parts.scheme.lower() in ("http", "https")
            and host
            and not is_telegram_host(host)
        ):
            return normalize_url(href)
    return None


def build_forwarded_post(
    message: Message, origin: MessageOriginChannel
) -> tuple[ForwardedChannel, RawPost] | None:
    """Card source and post for a forwarded channel post; None without text."""
    text = (message.text or message.caption or "").strip()
    if not text:
        return None
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
            job_link=_first_job_link(message),
            title=None,
            company=None,
            text=text[:MAX_TEXT_CHARS],
            posted_at=posted_at,
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

    built = build_forwarded_post(update.message, origin)
    if built is None:
        await context.bot.send_message(chat_id=chat_id, text=NO_TEXT_MESSAGE)
        return
    channel, post = built
    now = datetime.now(UTC).replace(tzinfo=None)
    outcome = await store_forwarded_post(async_session, user_id, channel, post, now)

    if outcome is ForwardOutcome.ADDED:
        reply = (
            ADDED_MESSAGE
            if await _has_description(user_id)
            else ADDED_NO_DESCRIPTION_MESSAGE
        )
    elif outcome is ForwardOutcome.MERGED:
        reply = MERGED_MESSAGE
    else:
        reply = ALREADY_SEEN_MESSAGE
    await context.bot.send_message(chat_id=chat_id, text=reply)
