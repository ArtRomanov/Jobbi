"""Lever job-board fetcher (public Postings API).

The region host comes from the source kind: ``lever`` -> ``api.lever.co``,
``lever_eu`` -> ``api.eu.lever.co``. A company that 404s in its own region is
not retried in the other one. Lever sends no gzip and always includes
descriptions, so postings are read in pages of 50 (~1 MB each).
"""

import re
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
import structlog

from app.discovery.fetchers.board_http import (
    cap_name,
    cap_text,
    check_handle,
    fits_columns,
    get_json,
    html_to_text,
    loggable_id,
)
from app.discovery.fetchers.errors import UNKNOWN_POSTED_AT, BoardReadError
from app.discovery.normalize import is_http_url, normalize_url
from app.discovery.types import RawPost

logger = structlog.get_logger()

LeverKind = Literal["lever", "lever_eu"]

API_HOSTS: dict[str, str] = {
    "lever": "https://api.lever.co",
    "lever_eu": "https://api.eu.lever.co",
}
PAGE_SIZE = 50
MAX_PAGES = 40

_SLUG_SPLIT_RE = re.compile(r"[-_]+")


def api_host(kind: str) -> str:
    """Return the API base URL for a Lever source kind.

    Raises:
        ValueError: ``kind`` is not a Lever kind.
    """
    try:
        return API_HOSTS[kind]
    except KeyError:
        raise ValueError(f"Not a Lever source kind: {kind!r}") from None


def display_name_from_slug(slug: str) -> str:
    """Title-case a Lever company slug: ``"acme-labs"`` -> ``"Acme Labs"``."""
    words = [word for word in _SLUG_SPLIT_RE.split(slug.strip()) if word]
    return " ".join(word.capitalize() for word in words) or slug


async def list_postings(
    client: httpx.AsyncClient,
    kind: str,
    company: str,
    page_size: int = PAGE_SIZE,
) -> list[dict[str, Any]]:
    """Return all published postings of a company, paging with ``skip``.

    Stops at the first page shorter than ``page_size`` (or after ``MAX_PAGES``
    pages as a safety net). Items without a string ``id`` or ``hostedUrl``
    are dropped, and so are items whose ``hostedUrl`` is not http(s) and items
    whose seen-key or URL would not fit the DB columns.

    Raises:
        BoardReadError: see ``board_http.get_json``.
        ValueError: ``kind`` is not a Lever kind.
    """
    url = f"{api_host(kind)}/v0/postings/{check_handle(company)}"
    postings: list[dict[str, Any]] = []
    for page in range(MAX_PAGES):
        data = await get_json(
            client,
            url,
            params={"mode": "json", "limit": page_size, "skip": page * page_size},
        )
        if not isinstance(data, list):
            raise BoardReadError("unreachable")
        postings.extend(item for item in data if _is_usable(kind, company, item))
        if len(data) < page_size:
            break
    else:
        logger.warning(
            "lever_page_limit_reached", kind=kind, company=company, pages=MAX_PAGES
        )
    return postings


def _is_usable(kind: str, company: str, item: Any) -> bool:
    if not (
        isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and isinstance(item.get("hostedUrl"), str)
        and bool(item["hostedUrl"])
    ):
        return False
    if not is_http_url(item["hostedUrl"]):
        logger.info(
            "lever_posting_url_rejected",
            kind=kind,
            board=company,
            job_id=item["id"],
        )
        return False
    if not fits_columns(posting_key(kind, company, item), item["hostedUrl"]):
        logger.info(
            "lever_posting_too_long",
            kind=kind,
            board=company,
            job_id=loggable_id(item["id"]),
        )
        return False
    return True


def _posting_text(posting: dict[str, Any]) -> str:
    parts: list[str] = []
    description = posting.get("descriptionPlain")
    if isinstance(description, str) and description.strip():
        parts.append(description.strip())
    lists = posting.get("lists")
    if isinstance(lists, list):
        for item in lists:
            if not isinstance(item, dict):
                continue
            heading = item.get("text")
            content = item.get("content")
            body = html_to_text(content) if isinstance(content, str) else ""
            block = "\n".join(
                p for p in (heading if isinstance(heading, str) else "", body) if p
            )
            if block:
                parts.append(block)
    return cap_text("\n\n".join(parts))


def posting_posted_at(posting: dict[str, Any]) -> datetime | None:
    """``createdAt`` (ms epoch) as naive UTC; None when missing or invalid."""
    value = posting.get("createdAt")
    if isinstance(value, int | float) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value / 1000, UTC).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def posting_key(kind: str, company: str, posting: dict[str, Any]) -> str:
    """The seen-key of a posting: ``lever:<company>/<id>`` / ``lever_eu:...``."""
    return f"{kind}:{company}/{posting['id']}"


async def check_company(client: httpx.AsyncClient, kind: str, company: str) -> None:
    """Verify the company has a board in this region with one small request.

    Raises:
        BoardReadError: ``not_found`` on 404 (the other region is not tried);
            ``unreachable`` otherwise (see ``board_http.get_json``).
        ValueError: ``kind`` is not a Lever kind.
    """
    url = f"{api_host(kind)}/v0/postings/{check_handle(company)}"
    data = await get_json(client, url, params={"mode": "json", "limit": 1})
    if not isinstance(data, list):
        raise BoardReadError("unreachable")


def to_raw_post(
    kind: str,
    company: str,
    posting: dict[str, Any],
    *,
    posted_at: datetime | None = None,
) -> RawPost:
    """Map a Lever posting to a ``RawPost``.

    Text is ``descriptionPlain`` plus the requirement lists, capped at
    20 000 chars. ``posted_at`` defaults to ``posting_posted_at``; a posting
    without a usable date gets ``UNKNOWN_POSTED_AT`` (treated as old).
    """
    hosted_url: str = posting["hostedUrl"]
    title = posting.get("text")
    if posted_at is None:
        posted_at = posting_posted_at(posting) or UNKNOWN_POSTED_AT
    return RawPost(
        external_key=posting_key(kind, company, posting),
        url=hosted_url,
        job_link=normalize_url(hosted_url),
        title=cap_name(title),
        company=cap_name(display_name_from_slug(company)),
        text=_posting_text(posting),
        posted_at=posted_at,
    )
