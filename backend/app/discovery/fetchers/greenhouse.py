"""Greenhouse job-board fetcher (public Job Board API).

All requests go to the fixed host ``boards-api.greenhouse.io``; EU board tokens
are served there too (verified 2026-11-22), only their job URLs differ.
"""

import asyncio
import html
from datetime import UTC, datetime
from typing import Any

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

API_BASE = "https://boards-api.greenhouse.io/v1/boards"
# Pause between two job-detail requests to the same board (politeness).
JOB_DETAIL_PAUSE_S = 1.0


def _board_url(token: str) -> str:
    return f"{API_BASE}/{check_handle(token)}"


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse a Greenhouse ISO-8601 timestamp (with offset) to naive UTC."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(UTC).replace(tzinfo=None)


async def fetch_board_name(client: httpx.AsyncClient, token: str) -> str:
    """Return the company name published on the board.

    Raises:
        BoardReadError: see ``board_http.get_json``.
    """
    data = await get_json(client, _board_url(token))
    raw = data.get("name") if isinstance(data, dict) else None
    # Same cleaning as job titles: no control, format or surrogate characters.
    name = " ".join((cap_name(raw) or "").split())
    if not name:
        raise BoardReadError("unreachable")
    return name


async def list_jobs(client: httpx.AsyncClient, token: str) -> list[dict[str, Any]]:
    """List the board's open jobs without their descriptions.

    Each item has ``id, title, absolute_url, location, first_published,
    updated_at, company_name``; ``location`` is the location name string.
    Entries without an id or an absolute http(s) URL are skipped, and so are
    entries whose seen-key or URL would not fit the DB columns.

    Raises:
        BoardReadError: see ``board_http.get_json``.
    """
    data = await get_json(
        client, f"{_board_url(token)}/jobs", headers={"Accept-Encoding": "gzip"}
    )
    raw_jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(raw_jobs, list):
        raise BoardReadError("unreachable")

    jobs: list[dict[str, Any]] = []
    for job in raw_jobs:
        if not isinstance(job, dict):
            continue
        job_id = job.get("id")
        absolute_url = job.get("absolute_url")
        if (
            not isinstance(job_id, int)
            or not isinstance(absolute_url, str)
            or not absolute_url
        ):
            continue
        if not is_http_url(absolute_url):
            logger.info("greenhouse_job_url_rejected", board=token, job_id=job_id)
            continue
        if not fits_columns(job_key(token, {"id": job_id}), absolute_url):
            logger.info(
                "greenhouse_job_too_long", board=token, job_id=loggable_id(job_id)
            )
            continue
        location = job.get("location")
        jobs.append(
            {
                "id": job_id,
                "title": job.get("title"),
                "absolute_url": absolute_url,
                "location": location.get("name")
                if isinstance(location, dict)
                else None,
                "first_published": job.get("first_published"),
                "updated_at": job.get("updated_at"),
                "company_name": job.get("company_name"),
            }
        )
    return jobs


async def fetch_job_text(client: httpx.AsyncClient, token: str, job_id: int) -> str:
    """Return one job's description as plain text (at most 20 000 chars).

    Greenhouse returns ``content`` as HTML-escaped HTML, so it is unescaped
    first and then converted to text.

    Raises:
        BoardReadError: see ``board_http.get_json``.
    """
    data = await get_json(
        client,
        f"{_board_url(token)}/jobs/{int(job_id)}",
        headers={"Accept-Encoding": "gzip"},
    )
    content = data.get("content") if isinstance(data, dict) else None
    if not isinstance(content, str):
        return ""
    # HTML -> text is CPU work on remote input: keep it off the event loop.
    return await asyncio.to_thread(_content_text, content)


def _content_text(content: str) -> str:
    return cap_text(html_to_text(html.unescape(content)))


def job_posted_at(job: dict[str, Any]) -> datetime | None:
    """``first_published``, else ``updated_at``, as naive UTC; None if neither parses."""
    return _parse_timestamp(job.get("first_published")) or _parse_timestamp(
        job.get("updated_at")
    )


def job_key(token: str, job: dict[str, Any]) -> str:
    """The seen-key of a job from ``list_jobs``: ``gh:<token>/<id>``."""
    return f"gh:{token}/{job['id']}"


def to_raw_post(
    token: str,
    job: dict[str, Any],
    text: str,
    *,
    posted_at: datetime | None = None,
) -> RawPost:
    """Map a job from ``list_jobs`` plus its text to a ``RawPost``.

    ``posted_at`` defaults to ``job_posted_at(job)``; a job without a usable
    date gets ``UNKNOWN_POSTED_AT`` (treated as old), never "now".
    """
    absolute_url: str = job["absolute_url"]
    if posted_at is None:
        posted_at = job_posted_at(job) or UNKNOWN_POSTED_AT
    title = job.get("title")
    company = job.get("company_name")
    return RawPost(
        external_key=job_key(token, job),
        url=absolute_url,
        job_link=normalize_url(absolute_url),
        title=cap_name(title),
        company=cap_name(company),
        text=cap_text(text),
        posted_at=posted_at,
    )
