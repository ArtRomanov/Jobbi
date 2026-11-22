"""Live check that a source exists and is public, before it is saved.

Requests only go to fixed hosts; the handle is the only user-derived part of
the URL and it has already been validated by `vacancy_source_parsing`.
"""

import asyncio

import httpx
import structlog
from bs4 import BeautifulSoup

logger = structlog.get_logger()

TELEGRAM_PREVIEW_URL = "https://t.me/s/{handle}"
USER_AGENT = "Jobbi/1.0"
CHECK_TIMEOUT_SECONDS = 10.0
# A channel preview page is ~100-300 KB; the header we need is at the top.
MAX_RESPONSE_BYTES = 1_000_000
MAX_DISPLAY_NAME_LENGTH = 255

CHANNEL_NOT_PUBLIC_MESSAGE = "This channel is not public or does not exist"
TELEGRAM_UNREACHABLE_MESSAGE = "Could not reach Telegram. Please try again."


class SourceCheckError(Exception):
    """Base for live-check failures; `message` is safe to show the user."""

    message: str = ""

    def __init__(self) -> None:
        super().__init__(self.message)


class SourceNotPublicError(SourceCheckError):
    """The source definitely does not exist or is not public."""

    message = CHANNEL_NOT_PUBLIC_MESSAGE


class SourceUnreachableError(SourceCheckError):
    """Network error or timeout: we could not tell either way."""

    message = TELEGRAM_UNREACHABLE_MESSAGE


async def _fetch_capped(client: httpx.AsyncClient, url: str) -> tuple[int, bytes]:
    """GET `url` without following redirects, reading at most the size cap."""
    async with client.stream("GET", url) as response:
        if response.status_code != httpx.codes.OK:
            return response.status_code, b""
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) >= MAX_RESPONSE_BYTES:
                del body[MAX_RESPONSE_BYTES:]
                break
        return response.status_code, bytes(body)


def _extract_channel_title(html: bytes, handle: str) -> str | None:
    """Return the channel title, `@handle` if untitled, None if not a channel page."""
    soup = BeautifulSoup(html, "html.parser")
    has_channel_info = soup.select_one(".tgme_channel_info") is not None
    has_messages = soup.select_one(".tgme_widget_message_wrap") is not None
    if not (has_channel_info or has_messages):
        return None
    title_node = soup.select_one(".tgme_channel_info_header_title")
    title = " ".join(title_node.get_text().split()) if title_node else ""
    return (title or f"@{handle}")[:MAX_DISPLAY_NAME_LENGTH]


async def fetch_telegram_channel_title(handle: str) -> str:
    """Check that `t.me/s/<handle>` is a public channel and return its title.

    Raises:
        SourceNotPublicError: redirect, 4xx, or a 200 page without channel content.
        SourceUnreachableError: network error, 429/5xx, or the 10 s total budget
            ran out.
    """
    url = TELEGRAM_PREVIEW_URL.format(handle=handle)
    try:
        async with (
            asyncio.timeout(CHECK_TIMEOUT_SECONDS),
            httpx.AsyncClient(
                timeout=CHECK_TIMEOUT_SECONDS,
                follow_redirects=False,
                headers={"User-Agent": USER_AGENT},
            ) as client,
        ):
            status_code, body = await _fetch_capped(client, url)
    except (TimeoutError, httpx.RequestError) as exc:
        logger.warning(
            "telegram_channel_check_failed", handle=handle, error=type(exc).__name__
        )
        raise SourceUnreachableError from exc

    if status_code == httpx.codes.TOO_MANY_REQUESTS or status_code >= 500:
        # Telegram is struggling; that says nothing about the channel.
        raise SourceUnreachableError
    if status_code != httpx.codes.OK:
        # 302 to t.me/<name> is how Telegram answers for unknown/private ones.
        raise SourceNotPublicError
    title = _extract_channel_title(body, handle)
    if title is None:
        raise SourceNotPublicError
    return title
