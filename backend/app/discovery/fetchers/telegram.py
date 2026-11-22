"""Read public Telegram channels through the `t.me/s/<channel>` web preview.

The page is unofficial HTML, so all markup knowledge lives in `parse_channel_page`
and is covered by fixture tests.
"""

import asyncio
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal, TypeAlias
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup, Tag

from app.discovery.normalize import normalize_url
from app.discovery.types import RawPost

__all__ = [
    "MAX_RESPONSE_BYTES",
    "MAX_TEXT_CHARS",
    "ReadFailureReason",
    "SourceReadError",
    "fetch_channel_posts",
    "parse_channel_page",
]

BASE_URL = "https://t.me/s/"
USER_AGENT = "Jobbi/1.0"
REQUEST_TIMEOUT_S = 15.0
PAGE_PAUSE_S = 1.0
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 20_000

# Telegram usernames: 5-32 chars, letters/digits/underscore. Accept 4+ for old
# short names. Anything else could change the request path, so it is rejected.
_CHANNEL_RE = re.compile(r"^[A-Za-z0-9_]{4,32}$")
_TELEGRAM_HOSTS = ("t.me", "telegram.me", "telegram.org")
_BLANK_LINES_RE = re.compile(r"\n{3,}")

ReadFailureReason: TypeAlias = Literal["private_or_deleted", "unreachable"]
SleepFn: TypeAlias = Callable[[float], Awaitable[None]]


class SourceReadError(Exception):
    """The channel could not be read.

    `reason` is "private_or_deleted" (redirect or 404: the channel has no public
    preview) or "unreachable" (network error, timeout, 429, 5xx, oversized or
    otherwise unexpected response).
    """

    def __init__(self, reason: ReadFailureReason, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason: ReadFailureReason = reason
        self.detail = detail


def _validate_channel(channel: str) -> str:
    if not _CHANNEL_RE.fullmatch(channel):
        raise ValueError(f"Invalid Telegram channel name: {channel!r}")
    return channel.lower()


def _is_telegram_host(host: str) -> bool:
    return any(
        host == domain or host.endswith(f".{domain}") for domain in _TELEGRAM_HOSTS
    )


def _message_text_element(message: Tag) -> Tag | None:
    """The post's own text block; skips the quoted text of a replied-to post."""
    for element in message.select(".tgme_widget_message_text"):
        if element.find_parent(class_="tgme_widget_message_reply") is None:
            return element
    return None


def _plain_text(element: Tag) -> str:
    for br in element.find_all("br"):
        br.replace_with("\n")
    lines = (line.rstrip() for line in element.get_text().splitlines())
    text = _BLANK_LINES_RE.sub("\n\n", "\n".join(lines)).strip()
    return text[:MAX_TEXT_CHARS]


def _first_job_link(element: Tag) -> str | None:
    for anchor in element.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        parts = urlsplit(href)
        if parts.scheme.lower() not in ("http", "https"):
            continue
        host = (parts.hostname or "").lower()
        if host and not _is_telegram_host(host):
            return normalize_url(href)
    return None


def _parse_posted_at(message: Tag) -> datetime | None:
    time_el = message.select_one(
        ".tgme_widget_message_date time[datetime]"
    ) or message.select_one("time[datetime]")
    if time_el is None:
        return None
    try:
        value = datetime.fromisoformat(str(time_el["datetime"]))
    except ValueError:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value


def parse_channel_page(html: str, channel: str) -> tuple[list[RawPost], int | None]:
    """Parse one `t.me/s/<channel>` page.

    Returns the posts of `channel` on the page (oldest first, as Telegram renders
    them) and the smallest post id seen, used for the next `?before=` page. Posts
    without a timestamp are skipped; media-only posts are kept with empty text.
    """
    channel_lc = _validate_channel(channel)
    soup = BeautifulSoup(html, "html.parser")
    posts: list[RawPost] = []
    oldest_id: int | None = None

    for message in soup.select(".tgme_widget_message[data-post]"):
        post_channel, _, raw_id = str(message["data-post"]).rpartition("/")
        if post_channel.lower() != channel_lc or not raw_id.isdigit():
            continue
        post_id = int(raw_id)
        oldest_id = post_id if oldest_id is None else min(oldest_id, post_id)

        posted_at = _parse_posted_at(message)
        if posted_at is None:
            continue
        text_el = _message_text_element(message)
        posts.append(
            RawPost(
                external_key=f"tg:{channel_lc}/{post_id}",
                url=f"https://t.me/{channel_lc}/{post_id}",
                job_link=_first_job_link(text_el) if text_el is not None else None,
                title=None,
                company=None,
                text=_plain_text(text_el) if text_el is not None else "",
                posted_at=posted_at,
            )
        )
    return posts, oldest_id


async def _get_page(client: httpx.AsyncClient, url: str, params: dict[str, str]) -> str:
    """GET one page with a size cap. Raises SourceReadError."""
    try:
        async with client.stream(
            "GET",
            url,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_S,
            follow_redirects=False,
        ) as response:
            status = response.status_code
            if response.is_redirect or status == 404:
                raise SourceReadError("private_or_deleted", f"HTTP {status}")
            if status != 200:
                raise SourceReadError("unreachable", f"HTTP {status}")
            declared = response.headers.get("content-length")
            if (
                declared is not None
                and declared.isdigit()
                and int(declared) > MAX_RESPONSE_BYTES
            ):
                raise SourceReadError("unreachable", "response too large")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise SourceReadError("unreachable", "response too large")
            return body.decode(response.encoding or "utf-8", errors="replace")
    except httpx.HTTPError as exc:
        raise SourceReadError("unreachable", type(exc).__name__) from exc


async def fetch_channel_posts(
    client: httpx.AsyncClient,
    channel: str,
    known_keys: set[str],
    cutoff: datetime,
    max_pages: int = 10,
    *,
    sleep: SleepFn = asyncio.sleep,
) -> list[RawPost]:
    """Read new posts of a public channel, newest pages first.

    Pages back with `?before=<oldest id>` and stops after a page that contains a
    known key or a post older than `cutoff` (naive UTC), on an empty page, or
    after `max_pages`. Known posts and posts older than the cutoff are not
    returned. Pauses `PAGE_PAUSE_S` between pages. Returns posts oldest first.

    Raises:
        ValueError: `channel` is not a valid Telegram username.
        SourceReadError: the channel could not be read.
    """
    channel_lc = _validate_channel(channel)
    url = f"{BASE_URL}{channel_lc}"
    found: dict[str, RawPost] = {}
    before: int | None = None

    for page in range(max_pages):
        if page:
            await sleep(PAGE_PAUSE_S)
        params = {"before": str(before)} if before is not None else {}
        html = await _get_page(client, url, params)
        posts, oldest_id = parse_channel_page(html, channel_lc)
        if oldest_id is None:
            break

        reached_end = False
        for post in posts:
            if post.external_key in known_keys or post.posted_at < cutoff:
                reached_end = True
            else:
                found.setdefault(post.external_key, post)

        if reached_end or (before is not None and oldest_id >= before):
            break
        before = oldest_id

    return sorted(found.values(), key=_post_order)


def _post_order(post: RawPost) -> tuple[datetime, int]:
    return post.posted_at, int(post.external_key.rsplit("/", 1)[1])
