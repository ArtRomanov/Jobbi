"""Read a web listing page by page (shared by the API and the hourly worker).

Every request goes through `fetchers/safe_http.py`. Pages are read in order,
one second apart, following the parser's next-page link only while it stays
on the same host; reading stops at the page limit, at a page with no new job
links, at the first page that cannot be read (only page 1 failing is an
error), or when the total time budget is spent.
"""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from app.discovery.fetchers import safe_http
from app.discovery.fetchers.safe_http import (
    PageFetchError,
    Resolver,
    UnsafeUrlError,
    fetch_html,
)
from app.discovery.fetchers.web_listing import AtsHint, ListingJob, parse_listing
from app.discovery.normalize import normalize_url

__all__ = [
    "MAX_LISTING_PAGES",
    "PAGE_PAUSE_SECONDS",
    "ListingRead",
    "read_listing",
    "web_seen_key",
]

MAX_LISTING_PAGES = 5
PAGE_PAUSE_SECONDS = 1.0

SleepFn = Callable[[float], Awaitable[None]]
StopFn = Callable[[list[ListingJob]], bool]


@dataclass(slots=True)
class ListingRead:
    """Jobs in page order (unique by normalized URL) and how many pages were read."""

    jobs: list[ListingJob] = field(default_factory=list)
    pages_read: int = 0
    # The job board page 1 links to most (preview hint only).
    ats_hint: AtsHint | None = None


def web_seen_key(source_id: str, job_url: str) -> str:
    """`web:<source_id>/<sha256(normalized job url)>` (fits String(255))."""
    digest = hashlib.sha256(normalize_url(job_url).encode("utf-8")).hexdigest()
    return f"web:{source_id}/{digest}"


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


async def read_listing(
    url: str,
    job_link_contains: str | None,
    *,
    max_pages: int = MAX_LISTING_PAGES,
    total_timeout_s: float,
    client: httpx.AsyncClient | None = None,
    resolver: Resolver | None = None,
    sleep: SleepFn = asyncio.sleep,
    pause_s: float | None = None,
    stop_after: StopFn | None = None,
) -> ListingRead:
    """Read up to `max_pages` pages of the listing at `url`.

    `stop_after(page_jobs)` may end the read after a page (the worker stops at
    a page that holds an already-seen job). Pages after the first that fail,
    redirect somewhere unsafe or do not fit the remaining time are simply not
    read; what was collected so far is returned.

    Raises:
        UnsafeUrlError: page 1 may not be fetched (scheme, port, address).
        PageFetchError: page 1 could not be read in time (see `reason`).
    """
    resolver = resolver or safe_http.system_resolver
    pause = PAGE_PAUSE_SECONDS if pause_s is None else pause_s
    loop = asyncio.get_running_loop()
    deadline = loop.time() + total_timeout_s

    result = ListingRead()
    seen_urls: set[str] = set()
    visited: set[str] = set()
    next_url: str | None = url
    own_client = client is None
    http = client or safe_http.make_client()
    try:
        while next_url is not None and result.pages_read < max_pages:
            page_url = next_url
            next_url = None
            visited.add(normalize_url(page_url))
            if result.pages_read > 0:
                if deadline - loop.time() <= pause:
                    break
                await sleep(pause)
            remaining = deadline - loop.time()
            if remaining <= 0:
                if result.pages_read == 0:
                    raise PageFetchError("unreachable")
                break
            try:
                page = await fetch_html(
                    page_url, client=http, resolver=resolver, timeout_s=remaining
                )
            except (UnsafeUrlError, PageFetchError):
                if result.pages_read == 0:
                    raise
                break
            result.pages_read += 1
            listing = parse_listing(page.text, page.final_url, job_link_contains)
            if result.pages_read == 1:
                result.ats_hint = listing.ats_hint
            new_jobs = [job for job in listing.jobs if job.url not in seen_urls]
            seen_urls.update(job.url for job in new_jobs)
            result.jobs.extend(new_jobs)
            if not new_jobs or (stop_after is not None and stop_after(new_jobs)):
                break
            candidate = listing.next_url
            if (
                candidate is not None
                and _host(candidate) == _host(page.final_url)
                and normalize_url(candidate) not in visited
            ):
                next_url = candidate
    finally:
        if own_client:
            await http.aclose()
    return result
