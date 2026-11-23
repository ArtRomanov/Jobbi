"""Ashby job-board fetcher (the public Posting API).

The only request goes to
``https://api.ashbyhq.com/posting-api/job-board/<org>?includeCompensation=false``;
the organization slug is the validated handle, so the host is fixed. One
answer holds every listed job with its full description (no paging, no
detail requests). An unknown organization answers 404.

The API does not expose the organization's name, so the display name is the
title-cased slug (as for Lever): ``acme-labs`` -> "Acme Labs".

Size: the answer carries every description twice (plain and HTML), so big
boards exceed the 5 MB board cap (measured 2026-11-23: openai 14.3 MB,
notion 3.1 MB, manychat 0.37 MB). This fixed-host request gets its own
``MAX_RESPONSE_BYTES`` (32 MB); the JSON is parsed in a worker thread.
"""

import asyncio
import re
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from app.discovery.fetchers.board_http import (
    cap_name,
    cap_text,
    fits_columns,
    get_bytes,
    html_to_text,
    loggable_id,
    parse_json_body,
)
from app.discovery.fetchers.errors import UNKNOWN_POSTED_AT, BoardReadError
from app.discovery.fetchers.lever import display_name_from_slug
from app.discovery.normalize import is_http_url, normalize_url
from app.discovery.types import RawPost

__all__ = [
    "MAX_JOBS",
    "MAX_RESPONSE_BYTES",
    "api_url",
    "check_board",
    "display_name",
    "job_key",
    "job_posted_at",
    "list_jobs",
    "parse_board",
    "to_raw_post",
]

logger = structlog.get_logger()

API_BASE = "https://api.ashbyhq.com/posting-api/job-board"
# A real board lists tens of jobs; more than this is not a job board.
MAX_JOBS = 2_000
# Decompressed body cap for this host only (see the module docstring).
MAX_RESPONSE_BYTES = 32 * 1024 * 1024

# The slug as stored (lowercased): 1-64 letters, digits, `.`, `_` or `-`,
# starting and ending with a letter or digit (`kraken.com` is a real board).
# `..` is refused separately.
_ORG_RE = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?", re.ASCII)
# Ashby job ids are UUIDs; anything path-like is refused.
_JOB_ID_RE = re.compile(r"[A-Za-z0-9-]{1,64}", re.ASCII)


def is_valid_org(org: str) -> bool:
    """True if ``org`` is a slug that may go into the API path."""
    return bool(_ORG_RE.fullmatch(org)) and ".." not in org


def api_url(org: str) -> str:
    """The Posting API URL of a board.

    Raises:
        BoardReadError: ``not_found`` if ``org`` is not a valid slug.
    """
    if not is_valid_org(org):
        raise BoardReadError("not_found")
    return f"{API_BASE}/{org}"


def display_name(org: str) -> str:
    """The board's display name: the title-cased slug."""
    return display_name_from_slug(org)


def job_key(org: str, job_id: str) -> str:
    """The seen-key of a job: ``ashby:<org>/<id>``."""
    return f"ashby:{org}/{job_id}"


def job_posted_at(job: dict[str, Any]) -> datetime | None:
    """``publishedAt`` (ISO 8601) as naive UTC; None when missing or invalid.

    A value without an offset is taken as UTC.
    """
    value = job.get("publishedAt")
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(UTC).replace(tzinfo=None)


def _is_usable(org: str, job: Any) -> bool:
    if not (
        isinstance(job, dict)
        and isinstance(job.get("id"), str)
        and _JOB_ID_RE.fullmatch(job["id"])
        and isinstance(job.get("jobUrl"), str)
        and job["jobUrl"]
    ):
        return False
    if job.get("isListed") is False:
        return False
    if not is_http_url(job["jobUrl"]):
        logger.info("ashby_job_url_rejected", board=org, job_id=job["id"])
        return False
    if not fits_columns(job_key(org, job["id"]), job["jobUrl"]):
        logger.info("ashby_job_too_long", board=org, job_id=loggable_id(job["id"]))
        return False
    return True


def parse_board(org: str, data: Any) -> list[dict[str, Any]]:
    """The usable jobs of a Posting API answer, deduplicated by id.

    A job needs a UUID-like string ``id`` and an http(s) ``jobUrl``; jobs
    marked ``isListed: false`` and jobs whose seen-key or URL would not fit
    the DB columns are dropped. At most ``MAX_JOBS`` entries are looked at.

    Raises:
        BoardReadError: ``unreachable`` if ``data`` is not ``{"jobs": [...]}``.
    """
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise BoardReadError("unreachable")
    entries = data["jobs"]
    if len(entries) > MAX_JOBS:
        logger.warning("ashby_job_limit_reached", board=org, jobs=len(entries))
    usable: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for job in entries[:MAX_JOBS]:
        if not _is_usable(org, job) or job["id"] in seen_ids:
            continue
        seen_ids.add(job["id"])
        usable.append(job)
    return usable


def _decode_board(org: str, body: bytes) -> list[dict[str, Any]]:
    return parse_board(org, parse_json_body(body))


async def list_jobs(client: httpx.AsyncClient, org: str) -> list[dict[str, Any]]:
    """Return the board's usable jobs (see ``parse_board``).

    The body (up to ``MAX_RESPONSE_BYTES``) is parsed in a worker thread.

    Raises:
        BoardReadError: ``not_found`` on 404 or an invalid slug;
            ``unreachable`` otherwise (see ``board_http.get_bytes``,
            ``board_http.parse_json_body`` and ``parse_board``).
    """
    body = await get_bytes(
        client,
        api_url(org),
        params={"includeCompensation": "false"},
        headers={"Accept": "application/json"},
        max_bytes=MAX_RESPONSE_BYTES,
    )
    return await asyncio.to_thread(_decode_board, org, body)


async def check_board(client: httpx.AsyncClient, org: str) -> None:
    """Verify the board exists and answers in the expected shape.

    Raises:
        BoardReadError: see ``list_jobs``.
    """
    await list_jobs(client, org)


def _job_text(job: dict[str, Any]) -> str:
    plain = job.get("descriptionPlain")
    if isinstance(plain, str) and plain.strip():
        return cap_text(plain.strip())
    markup = job.get("descriptionHtml")
    if isinstance(markup, str):
        return cap_text(html_to_text(markup))
    return ""


def to_raw_post(
    org: str,
    job: dict[str, Any],
    *,
    posted_at: datetime | None = None,
) -> RawPost:
    """Map a usable Ashby job to a ``RawPost``.

    Text is ``descriptionPlain`` (else ``descriptionHtml`` as text), capped at
    20 000 chars; HTML conversion is CPU work, so async callers run this in a
    worker thread. ``posted_at`` defaults to ``job_posted_at``; a job without
    a usable date gets ``UNKNOWN_POSTED_AT`` (treated as old). The job link is
    stored, never fetched.
    """
    job_url: str = job["jobUrl"]
    if posted_at is None:
        posted_at = job_posted_at(job) or UNKNOWN_POSTED_AT
    return RawPost(
        external_key=job_key(org, job["id"]),
        url=job_url,
        job_link=normalize_url(job_url),
        title=cap_name(job.get("title")),
        company=cap_name(display_name(org)),
        text=_job_text(job),
        posted_at=posted_at,
    )
