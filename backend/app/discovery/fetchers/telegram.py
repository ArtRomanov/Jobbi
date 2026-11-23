"""Read public Telegram channels through the `t.me/s/<channel>` web preview.

The page is unofficial HTML, so all markup knowledge lives in `parse_channel_page`
and is covered by fixture tests.
"""

import asyncio
import re
from bisect import bisect_right
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from itertools import islice
from typing import Literal, TypeAlias
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup, Tag

from app.discovery.normalize import normalize_url
from app.discovery.types import MAX_LINK_CHARS, PostLink, RawPost

__all__ = [
    "MAX_RESPONSE_BYTES",
    "MAX_TEXT_CHARS",
    "ReadFailureReason",
    "SourceReadError",
    "fetch_channel_posts",
    "is_telegram_host",
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


def is_telegram_host(host: str) -> bool:
    return any(
        host == domain or host.endswith(f".{domain}") for domain in _TELEGRAM_HOSTS
    )


def _message_text_element(message: Tag) -> Tag | None:
    """The post's own text block; skips the quoted text of a replied-to post."""
    for element in message.select(".tgme_widget_message_text"):
        if element.find_parent(class_="tgme_widget_message_reply") is None:
            return element
    return None


def _link_url(href: str) -> str | None:
    """`href` normalized if it is an http(s) link outside Telegram, else None."""
    href = href.strip()
    try:
        parts = urlsplit(href)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https"):
        return None
    host = (parts.hostname or "").lower()
    if not host or is_telegram_host(host):
        return None
    return normalize_url(href)


def _first_job_link(element: Tag) -> str | None:
    for anchor in element.find_all("a", href=True):
        if (link := _link_url(str(anchor["href"]))) is not None:
            return link
    return None


def _free_chars(text: str, count: int) -> list[str]:
    """`count` private-use characters that do not occur in `text`."""
    used = set(text)
    return list(
        islice((c for c in map(chr, range(0xE000, 0xF900)) if c not in used), count)
    )


def _normalize_lines(raw: str) -> tuple[str, Callable[[int], int]]:
    """The stored plain text of `raw` and a map from raw to stored offsets.

    Lines are right-stripped, leading/trailing blank lines dropped, each run of
    blank lines collapsed to one and the first line left-stripped: the same as
    `"\n".join(rstripped lines)`, 3+ newlines -> 2, `.strip()`. The offset map
    is only valid for offsets of non-whitespace characters (those always
    survive normalization).
    """
    out: list[str] = []
    raw_starts: list[int] = []
    out_index: list[int] = []  # per raw line; -1 for dropped (blank) lines
    pending_blank = False
    position = 0
    for raw_line in raw.splitlines(keepends=True):
        raw_starts.append(position)
        position += len(raw_line)
        line = raw_line.rstrip()
        if not line:
            pending_blank = bool(out)
            out_index.append(-1)
            continue
        if pending_blank:
            out.append("")
            pending_blank = False
        out_index.append(len(out))
        out.append(line)

    lead = 0
    if out:
        lead = len(out[0]) - len(out[0].lstrip())
        out[0] = out[0][lead:]
    out_starts: list[int] = []
    position = 0
    for line in out:
        out_starts.append(position)
        position += len(line) + 1

    def to_stored(offset: int) -> int:
        raw_line = bisect_right(raw_starts, offset) - 1
        line = out_index[raw_line]
        column = offset - raw_starts[raw_line] - (lead if line == 0 else 0)
        return out_starts[line] + column

    return "\n".join(out), to_stored


def _text_and_links(element: Tag) -> tuple[str, tuple[PostLink, ...]]:
    """The post's plain text (capped) and its outside links with their lines.

    Each kept anchor's content is wrapped in two marker characters that do not
    occur in the post, so after `get_text()` the markers give the anchor's span
    in the raw text. The line is that of the anchor's first visible character
    in the final text; anchors without visible text or cut off by
    `MAX_TEXT_CHARS` are dropped.
    """
    for br in element.find_all("br"):
        br.replace_with("\n")
    marks = _free_chars(element.get_text(), 2)
    if len(marks) < 2:  # a post using every private-use character: no links
        text, _ = _normalize_lines(element.get_text())
        return text[:MAX_TEXT_CHARS], ()
    start_mark, end_mark = marks
    urls: list[str] = []
    for anchor in element.find_all("a", href=True):
        url = _link_url(str(anchor["href"]))
        if url is None or len(url) > MAX_LINK_CHARS:
            continue
        anchor.insert(0, start_mark)
        anchor.append(end_mark)
        urls.append(url)

    chars: list[str] = []
    spans: dict[int, tuple[int, int]] = {}
    open_anchors: list[tuple[int, int]] = []
    opened = 0
    for char in element.get_text():
        if char == start_mark:
            open_anchors.append((opened, len(chars)))
            opened += 1
        elif char == end_mark:
            if open_anchors:
                index, start = open_anchors.pop()
                spans[index] = (start, len(chars))
        else:
            chars.append(char)
    raw = "".join(chars)

    text, to_stored = _normalize_lines(raw)
    text = text[:MAX_TEXT_CHARS]
    links: list[PostLink] = []
    for index, url in enumerate(urls):
        if index not in spans:
            continue
        start, end = spans[index]
        visible = next((i for i in range(start, end) if not raw[i].isspace()), None)
        if visible is None:
            continue
        offset = to_stored(visible)
        if offset >= len(text):
            continue
        link = PostLink(line=text.count("\n", 0, offset) + 1, url=url)
        if link not in links:
            links.append(link)
    return text, tuple(links)


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
        # ASCII only: str.isdigit() also accepts "²" (int() then raises and the
        # whole channel fails) and Arabic-Indic digits (int() maps them onto
        # another post's key).
        if (
            post_channel.lower() != channel_lc
            or not raw_id.isascii()
            or not raw_id.isdigit()
        ):
            continue
        post_id = int(raw_id)
        oldest_id = post_id if oldest_id is None else min(oldest_id, post_id)

        posted_at = _parse_posted_at(message)
        if posted_at is None:
            continue
        text_el = _message_text_element(message)
        job_link: str | None = None
        text = ""
        links: tuple[PostLink, ...] = ()
        if text_el is not None:
            job_link = _first_job_link(text_el)
            text, links = _text_and_links(text_el)
        posts.append(
            RawPost(
                external_key=f"tg:{channel_lc}/{post_id}",
                url=f"https://t.me/{channel_lc}/{post_id}",
                job_link=job_link,
                title=None,
                company=None,
                text=text,
                posted_at=posted_at,
                links=links,
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
