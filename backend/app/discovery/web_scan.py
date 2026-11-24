"""Read a web listing page by page (shared by the API and the hourly worker).

Every request goes through `fetchers/safe_http.py`. Pages are read in order,
one second apart, following the parser's next-page link only while it stays
on the same host; reading stops at the page limit, at a page with no new job
links, at the first page that cannot be read (only page 1 failing is an
error), or when the total time budget is spent.

A link a site listing adapter knows (`fetchers/site_listing.py`, e.g. a
geekjob.ru search) is read from the site's JSON endpoint instead, page by
page through `safe_http.fetch_json`, with the same limits and stop rules;
its next page is built by the adapter (fixed host), not taken from the page.
"""

import asyncio
import hashlib
import inspect
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
    fetch_json,
)
from app.discovery.fetchers.site_listing import SiteListing, find_site_listing
from app.discovery.fetchers.web_listing import (
    AtsHint,
    ListingJob,
    ListingPage,
    parse_listing,
)
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
# Sync (`def f(jobs) -> bool`) or async (`async def f(jobs) -> bool`).
StopFn = Callable[[list[ListingJob]], bool | Awaitable[bool]]


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


async def _should_stop(stop_after: StopFn | None, page_jobs: list[ListingJob]) -> bool:
    if stop_after is None:
        return False
    verdict = stop_after(page_jobs)
    if inspect.isawaitable(verdict):
        verdict = await verdict
    return bool(verdict)


async def _read_page(
    site: SiteListing | None,
    page_url: str,
    page_number: int,
    job_link_contains: str | None,
    *,
    client: httpx.AsyncClient,
    resolver: Resolver,
    timeout_s: float,
) -> tuple[ListingPage, str]:
    """Fetch and parse one listing page; returns it and its final URL.

    Parsing is CPU work (a hostile page can take seconds): it runs in a
    worker thread, off the event loop the API and the worker share.

    Raises:
        UnsafeUrlError, PageFetchError: from ``safe_http``.
    """
    if site is None:
        page = await fetch_html(
            page_url, client=client, resolver=resolver, timeout_s=timeout_s
        )
        listing = await asyncio.to_thread(
            parse_listing, page.text, page.final_url, job_link_contains
        )
        return listing, page.final_url
    document = await fetch_json(
        page_url,
        client=client,
        resolver=resolver,
        timeout_s=timeout_s,
        max_redirects=site.max_redirects,
    )
    listing = await asyncio.to_thread(
        site.parse_page, document.data, page_number, job_link_contains
    )
    return listing, document.final_url


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
    a page that holds an already-seen job). It gets the page's new jobs (never
    empty) and returns a bool, either directly (`def`) or as an awaitable
    (`async def`, e.g. a DB lookup), which is awaited; truthy means stop. It
    is called once per page, after that page's jobs were added to the result;
    an exception from it propagates. Each page is parsed in a worker thread
    (`asyncio.to_thread`). Pages after the first that fail,
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

    site = find_site_listing(url)
    result = ListingRead()
    seen_urls: set[str] = set()
    visited: set[str] = set()
    next_url: str | None = url if site is None else site.page_url(1)
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
                listing, final_url = await _read_page(
                    site,
                    page_url,
                    result.pages_read + 1,
                    job_link_contains,
                    client=http,
                    resolver=resolver,
                    timeout_s=remaining,
                )
            except (UnsafeUrlError, PageFetchError):
                if result.pages_read == 0:
                    raise
                break
            result.pages_read += 1
            if result.pages_read == 1:
                result.ats_hint = listing.ats_hint
            new_jobs = [job for job in listing.jobs if job.url not in seen_urls]
            seen_urls.update(job.url for job in new_jobs)
            result.jobs.extend(new_jobs)
            if new_jobs:
                if await _should_stop(stop_after, new_jobs):
                    break
            elif site is None or listing.skipped_count == 0:
                break
            # else: an adapter page whose entries were all unusable (e.g.
            # archived) is not the end of the listing; keep paging.
            candidate = listing.next_url
            if (
                candidate is not None
                # An adapter builds its next page on its own fixed host.
                and (site is not None or _host(candidate) == _host(final_url))
                and normalize_url(candidate) not in visited
            ):
                next_url = candidate
    finally:
        if own_client:
            await http.aclose()
    return result
