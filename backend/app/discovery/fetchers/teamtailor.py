"""Teamtailor company-board fetcher (the public ``/jobs.rss`` feed).

The only request goes to ``https://<sub>.teamtailor.com/jobs.rss``; the
subdomain is the validated handle, so the host is fixed per source.

The feed is parsed with lxml with entity resolution, network access and huge
trees disabled, and any document that carries a DOCTYPE is refused outright:
RSS never needs one, and that is where XML bombs (billion laughs) and external
entities live.
"""

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx
import structlog
from lxml import etree

from app.discovery.fetchers.board_http import (
    cap_name,
    cap_text,
    fits_columns,
    get_bytes,
    html_to_text,
)
from app.discovery.fetchers.errors import UNKNOWN_POSTED_AT, BoardReadError
from app.discovery.normalize import is_http_url, normalize_url
from app.discovery.types import RawPost

__all__ = [
    "TeamtailorFeed",
    "TeamtailorItem",
    "feed_url",
    "fetch_board_name",
    "fetch_feed",
    "item_key",
    "parse_feed",
    "to_raw_post",
]

logger = structlog.get_logger()

# A DNS label: 1-63 lowercase letters, digits or dashes, no dash at either end.
_SUBDOMAIN_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.ASCII)
# `/jobs/<numeric id>-<slug>` (or just `/jobs/<id>`) in an item link.
_JOB_ID_RE = re.compile(r"/jobs/(\d{1,20})(?:-[^/]*)?/?", re.ASCII)


@dataclass(frozen=True, slots=True, kw_only=True)
class TeamtailorItem:
    job_id: str
    link: str
    title: str | None
    description_html: str
    posted_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class TeamtailorFeed:
    company: str | None
    items: list[TeamtailorItem]


def feed_url(subdomain: str) -> str:
    """The feed URL of a board.

    Raises:
        BoardReadError: ``not_found`` if ``subdomain`` is not a valid label.
    """
    if not _SUBDOMAIN_RE.fullmatch(subdomain):
        raise BoardReadError("not_found")
    return f"https://{subdomain}.teamtailor.com/jobs.rss"


def _make_parser() -> etree.XMLParser:
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
        load_dtd=False,
        dtd_validation=False,
        attribute_defaults=False,
        recover=False,
    )


def _child_text(element: etree._Element, tag: str) -> str:
    child = element.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _parse_pub_date(value: str) -> datetime | None:
    """RFC 822 ``pubDate`` as naive UTC; None if missing or invalid."""
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(UTC).replace(tzinfo=None)


def _job_id(link: str) -> str | None:
    try:
        path = urlsplit(link).path
    except ValueError:
        return None
    match = _JOB_ID_RE.fullmatch(path)
    return match[1] if match else None


def parse_feed(subdomain: str, body: bytes) -> TeamtailorFeed:
    """Parse a ``jobs.rss`` body.

    Items without an http(s) link of the form ``/jobs/<id>-<slug>`` are
    skipped, and so are items whose seen-key or URL would not fit the DB
    columns.

    Raises:
        BoardReadError: ``unreachable`` for malformed XML, a document with a
            DOCTYPE, or a document that is not an RSS feed with a channel.
    """
    try:
        root = etree.fromstring(body, parser=_make_parser())
    except etree.XMLSyntaxError as exc:
        raise BoardReadError("unreachable") from exc
    if root.getroottree().docinfo.doctype:
        logger.warning("teamtailor_feed_doctype_rejected", board=subdomain)
        raise BoardReadError("unreachable")
    channel = root.find("channel") if root.tag == "rss" else None
    if channel is None:
        raise BoardReadError("unreachable")

    items: list[TeamtailorItem] = []
    seen_ids: set[str] = set()
    for element in channel.iterfind("item"):
        link = _child_text(element, "link")
        job_id = _job_id(link) if link and is_http_url(link) else None
        if job_id is None:
            logger.info("teamtailor_item_link_rejected", board=subdomain)
            continue
        if job_id in seen_ids:
            continue
        if not fits_columns(item_key(subdomain, job_id), link):
            logger.info("teamtailor_item_too_long", board=subdomain, job_id=job_id)
            continue
        seen_ids.add(job_id)
        items.append(
            TeamtailorItem(
                job_id=job_id,
                link=link,
                title=_child_text(element, "title") or None,
                description_html=_child_text(element, "description"),
                posted_at=_parse_pub_date(_child_text(element, "pubDate")),
            )
        )
    return TeamtailorFeed(company=_child_text(channel, "title") or None, items=items)


async def fetch_feed(client: httpx.AsyncClient, subdomain: str) -> TeamtailorFeed:
    """Read and parse the board's feed.

    Raises:
        BoardReadError: ``not_found`` on 404 or an invalid subdomain;
            ``unreachable`` otherwise (see ``board_http.get_bytes`` and
            ``parse_feed``).
    """
    body = await get_bytes(
        client,
        feed_url(subdomain),
        headers={"Accept": "application/rss+xml, application/xml;q=0.9"},
    )
    # Up to 5 MB of XML: parse it in a worker thread, off the event loop.
    return await asyncio.to_thread(parse_feed, subdomain, body)


async def fetch_board_name(client: httpx.AsyncClient, subdomain: str) -> str:
    """Return the company name (the channel title) of a readable board.

    Raises:
        BoardReadError: see ``fetch_feed``; ``unreachable`` if the channel
            has no title.
    """
    feed = await fetch_feed(client, subdomain)
    if feed.company is None:
        raise BoardReadError("unreachable")
    return feed.company


def item_key(subdomain: str, job_id: str) -> str:
    """The seen-key of a job: ``tt:<sub>/<id>``."""
    return f"tt:{subdomain}/{job_id}"


def to_raw_post(
    subdomain: str,
    company: str | None,
    item: TeamtailorItem,
    *,
    posted_at: datetime | None = None,
) -> RawPost:
    """Map a feed item to a ``RawPost``.

    ``posted_at`` defaults to the item's ``pubDate``; an undated item gets
    ``UNKNOWN_POSTED_AT`` (treated as old).
    """
    if posted_at is None:
        posted_at = item.posted_at or UNKNOWN_POSTED_AT
    return RawPost(
        external_key=item_key(subdomain, item.job_id),
        url=item.link,
        job_link=normalize_url(item.link),
        title=cap_name(item.title),
        company=cap_name(company),
        text=cap_text(html_to_text(item.description_html)),
        posted_at=posted_at,
    )
