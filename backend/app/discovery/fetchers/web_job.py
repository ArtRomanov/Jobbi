"""Read one job page of a ``web`` source into text plus a few fields.

Order:

1. JSON-LD: every ``<script type="application/ld+json">`` block (a single
   object, an array, or an object with ``@graph``; blocks that are not valid
   JSON are skipped). The first object whose ``@type`` is ``JobPosting`` (or
   a list containing it) gives ``description`` (HTML -> text),
   ``datePosted``, ``title`` and ``hiringOrganization.name``.
2. No JobPosting, or its description is empty: ``trafilatura.extract`` on the
   HTML that ``safe_http`` already fetched. Trafilatura's own downloader is
   never used, it would bypass the SSRF guard.
   Skipped for pages over ``_MAX_EXTRACT_ELEMENTS`` elements (its cost is
   per element; a 5 MB page of empty tags would take about a minute).
3. Trafilatura found nothing (or was skipped): plain text of ``<main>``, else ``<article>``,
   else ``<body>``.

HTML is parsed with lxml, which stops nesting at a fixed depth (~255), and
converted to text in one linear pass (``board_http.parse_html`` /
``element_text`` / ``html_to_text``, shared with the board fetchers).

Parsing never raises on bad input: a page it can't read gives empty text,
and an unexpected failure (e.g. ``RecursionError``) gives an empty page.
"""

import asyncio
import datetime as dt
import html as html_lib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import islice
from typing import Any

import httpx
import structlog
import trafilatura
from lxml import etree

from app.discovery.fetchers.board_http import (
    NOISE_TAGS,
    cap_name,
    cap_text,
    element_text,
    html_to_text,
    parse_html,
)
from app.discovery.fetchers.safe_http import Resolver, fetch_html, system_resolver

__all__ = ["JobPage", "fetch_job", "parse_job_page"]

logger = structlog.get_logger()

_JOB_POSTING = "JobPosting"
_LD_JSON = "application/ld+json"
_MAX_JSON_LD_NODES = 2_000  # objects visited per page, against huge graphs
_MAX_DATE_CHARS = 64
# Real job pages have a few hundred to a few thousand elements; trafilatura
# spends ~0.1 ms per element, so a bigger (likely hostile) page skips it.
_MAX_EXTRACT_ELEMENTS = 30_000
_CONTENT_TAGS = ("main", "article", "body")


@dataclass(frozen=True, slots=True)
class JobPage:
    """One job page: plain text (may be empty) and optional fields."""

    text: str
    posted_at: dt.datetime | None  # naive UTC
    title: str | None
    company: str | None


_EMPTY = JobPage(text="", posted_at=None, title=None, company=None)


@dataclass(frozen=True, slots=True)
class _Posting:
    description: str
    posted_at: dt.datetime | None
    title: str | None
    company: str | None


def _short(value: Any) -> str | None:
    """A non-empty single-line string cut to the name column, else None."""
    if not isinstance(value, str):
        return None
    return cap_name(" ".join(html_lib.unescape(value).split()))


def _parse_date(value: Any) -> dt.datetime | None:
    """ISO date or datetime -> naive UTC; a date alone is midnight UTC."""
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw or len(raw) > _MAX_DATE_CHARS:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            # 0001-01-01T00:00+01:00 / 9999-12-31T23:59-01:00 leave the
            # datetime range when shifted to UTC: OverflowError.
            parsed = parsed.astimezone(dt.UTC).replace(tzinfo=None)
    except (ValueError, TypeError, OverflowError):
        return None
    return parsed


def _is_job_posting(node: dict[str, Any]) -> bool:
    kind = node.get("@type")
    if isinstance(kind, list):
        return _JOB_POSTING in kind
    return kind == _JOB_POSTING


def _json_ld_objects(root: etree._Element) -> Iterator[dict[str, Any]]:
    """Every object in the page's JSON-LD blocks, arrays and ``@graph`` opened."""
    visited = 0
    for script in root.iter("script"):
        if (script.get("type") or "").strip().lower() != _LD_JSON:
            continue
        try:
            data = json.loads(script.text or "")
        except (ValueError, RecursionError):
            continue
        stack: list[Any] = [data]
        while stack:
            visited += 1
            if visited > _MAX_JSON_LD_NODES:
                return
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(reversed(item))
            elif isinstance(item, dict):
                yield item
                graph = item.get("@graph")
                if isinstance(graph, list | dict):
                    stack.append(graph)


def _description_text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    if "<" not in value and "&lt;" in value:
        value = html_lib.unescape(value)  # HTML sent escaped once more
    return html_to_text(value)


def _company(value: Any) -> str | None:
    if isinstance(value, list) and value:
        value = value[0]
    if isinstance(value, dict):
        value = value.get("name")
    return _short(value)


def _find_posting(root: etree._Element) -> _Posting | None:
    for node in _json_ld_objects(root):
        if _is_job_posting(node):
            return _Posting(
                description=_description_text(node.get("description")),
                posted_at=_parse_date(node.get("datePosted")),
                title=_short(node.get("title")),
                company=_company(node.get("hiringOrganization")),
            )
    return None


def _trafilatura_text(html: str, page_url: str) -> str:
    """Main text by trafilatura; "" if it finds nothing or fails.

    Only the pure ``extract`` is called; ``url`` is used for metadata, it is
    not downloaded.
    """
    try:
        text = trafilatura.extract(
            html,
            url=page_url,
            output_format="txt",
            include_comments=False,
            include_tables=True,
            include_images=False,
            include_links=False,
            favor_recall=True,
        )
    # A third-party parser on hostile input: any failure means "no text".
    except Exception as exc:  # noqa: BLE001
        logger.warning("web_job_extract_failed", error=type(exc).__name__)
        return ""
    return (text or "").strip()


def _is_huge(root: etree._Element) -> bool:
    """More elements than trafilatura handles quickly (~0.1 ms each)."""
    return next(islice(root.iter(), _MAX_EXTRACT_ELEMENTS, None), None) is not None


def _fallback_text(root: etree._Element) -> str:
    etree.strip_elements(root, *NOISE_TAGS, with_tail=False)
    for name in _CONTENT_TAGS:
        found = next(root.iter(name), None)
        if found is not None:
            text = element_text(found)
            if text:
                return text
    return ""


def parse_job_page(html: str, page_url: str) -> JobPage:
    """Text, date, title and company of one job page (pure, no network).

    ``page_url`` is the URL the page was fetched from (after redirects).
    Never raises: a page that breaks the parser gives an empty ``JobPage``
    (the caller then treats it like a page without text).
    """
    try:
        return _parse_job_page(html, page_url)
    # Hostile input in third-party parsers (lxml, json, trafilatura,
    # datetime): any failure means "nothing readable", never a crashed run.
    except Exception as exc:  # noqa: BLE001
        logger.warning("web_job_parse_failed", error=type(exc).__name__)
        return _EMPTY


def _parse_job_page(html: str, page_url: str) -> JobPage:
    root = parse_html(html) if html.strip() else None
    if root is None:
        return _EMPTY

    posting = _find_posting(root)
    text = posting.description if posting is not None else ""
    if not text and not _is_huge(root):
        text = _trafilatura_text(html, page_url)
    if not text:
        text = _fallback_text(root)
    return JobPage(
        text=cap_text(text),
        posted_at=posting.posted_at if posting else None,
        title=posting.title if posting else None,
        company=posting.company if posting else None,
    )


async def fetch_job(
    url: str,
    *,
    client: httpx.AsyncClient,
    resolver: Resolver = system_resolver,
) -> JobPage:
    """Fetch a job page through the SSRF guard and parse it.

    Raises:
        UnsafeUrlError: the URL or a redirect hop may not be fetched.
        PageFetchError: the page could not be read.
    """
    page = await fetch_html(url, client=client, resolver=resolver)
    # Parsing a large page is CPU work; keep it off the event loop.
    return await asyncio.to_thread(parse_job_page, page.text, page.final_url)
