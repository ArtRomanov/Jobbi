"""Live check that a source exists and is public, before it is saved.

Channel and board requests only go to fixed hosts; the handle is the only
user-derived part of the URL and it has already been validated by
`vacancy_source_parsing`. Web page URLs are user-supplied as a whole and are
fetched only through the SSRF-guarded `safe_http` (via `web_scan`).
"""

import asyncio
import functools
import weakref

import httpx
import structlog
from bs4 import BeautifulSoup

from app.discovery import web_scan
from app.discovery.fetchers import ashby, greenhouse, lever, teamtailor
from app.discovery.fetchers.errors import BLOCKED_MESSAGE, BoardReadError
from app.discovery.fetchers.safe_http import PageFetchError, UnsafeUrlError
from app.services.vacancy_source_parsing import UNSAFE_LINK_MESSAGE

logger = structlog.get_logger()

TELEGRAM_PREVIEW_URL = "https://t.me/s/{handle}"
USER_AGENT = "Jobbi/1.0"
CHECK_TIMEOUT_SECONDS = 10.0
# Total limit of one Ashby read, which may outlive its check (see
# `check_ashby_board`): it holds the one Ashby slot until it ends.
ASHBY_READ_LIMIT_SECONDS = 30.0
# A channel preview page is ~100-300 KB; the header we need is at the top.
MAX_RESPONSE_BYTES = 1_000_000
MAX_DISPLAY_NAME_LENGTH = 255

CHANNEL_NOT_PUBLIC_MESSAGE = "This channel is not public or does not exist"
TELEGRAM_UNREACHABLE_MESSAGE = "Could not reach Telegram. Please try again."
BOARD_UNREADABLE_MESSAGE = "Could not read this job board"


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


class BoardUnreadableError(SourceCheckError):
    """The job board does not exist (404) or could not be read in time."""

    message = BOARD_UNREADABLE_MESSAGE


class SiteBlockedError(SourceCheckError):
    """The page or board API answered with a bot-protection challenge."""

    message = BLOCKED_MESSAGE


def _board_check_error(exc: BaseException) -> SourceCheckError:
    """The user-facing error for a failed board check."""
    if isinstance(exc, BoardReadError) and exc.reason == "blocked":
        return SiteBlockedError()
    return BoardUnreadableError()


# One Ashby live check at a time per event loop: an answer may be 32 MB and
# its parse thread outlives the 10 s timeout, so parallel adds would stack
# up memory. Keyed by loop because an asyncio.Semaphore binds to one loop.
_ashby_slots: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()


def _ashby_slot() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    slot = _ashby_slots.get(loop)
    if slot is None:
        slot = _ashby_slots[loop] = asyncio.Semaphore(1)
    return slot


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


async def fetch_greenhouse_board_name(token: str) -> str:
    """Check that the Greenhouse board exists and return its published name.

    Raises:
        BoardUnreadableError: unknown board (404), network error, timeout, an
            unexpected response, or the 10 s total budget ran out.
    """
    try:
        async with (
            asyncio.timeout(CHECK_TIMEOUT_SECONDS),
            httpx.AsyncClient(timeout=CHECK_TIMEOUT_SECONDS) as client,
        ):
            name = await greenhouse.fetch_board_name(client, token)
    except (TimeoutError, BoardReadError) as exc:
        logger.warning(
            "greenhouse_board_check_failed",
            token=token,
            error=getattr(exc, "reason", type(exc).__name__),
        )
        raise _board_check_error(exc) from exc
    return name[:MAX_DISPLAY_NAME_LENGTH]


async def check_lever_board(kind: str, company: str) -> str:
    """Check that the Lever company exists in its region; return its display name.

    Lever's postings API has no company-name field, so the name is derived
    from the slug (`acme-labs` -> "Acme Labs").

    Raises:
        BoardUnreadableError: unknown company in this region (404; the other
            region is not tried), network error, timeout, an unexpected
            response, or the 10 s total budget ran out.
    """
    try:
        async with (
            asyncio.timeout(CHECK_TIMEOUT_SECONDS),
            httpx.AsyncClient(timeout=CHECK_TIMEOUT_SECONDS) as client,
        ):
            await lever.check_company(client, kind, company)
    except (TimeoutError, BoardReadError) as exc:
        logger.warning(
            "lever_board_check_failed",
            kind=kind,
            company=company,
            error=getattr(exc, "reason", type(exc).__name__),
        )
        raise _board_check_error(exc) from exc
    return lever.display_name_from_slug(company)[:MAX_DISPLAY_NAME_LENGTH]


async def fetch_teamtailor_board_name(subdomain: str) -> str:
    """Check that the Teamtailor feed is readable and return the company name.

    Raises:
        BoardUnreadableError: unknown board (404), network error, timeout, a
            malformed or untitled feed, or the 10 s total budget ran out.
    """
    try:
        async with (
            asyncio.timeout(CHECK_TIMEOUT_SECONDS),
            httpx.AsyncClient(timeout=CHECK_TIMEOUT_SECONDS) as client,
        ):
            name = await teamtailor.fetch_board_name(client, subdomain)
    except (TimeoutError, BoardReadError) as exc:
        logger.warning(
            "teamtailor_board_check_failed",
            subdomain=subdomain,
            error=getattr(exc, "reason", type(exc).__name__),
        )
        raise _board_check_error(exc) from exc
    return name[:MAX_DISPLAY_NAME_LENGTH]


async def check_ashby_board(org: str) -> str:
    """Check that the Ashby board is readable; return its display name.

    The Posting API has no organization-name field, so the name is derived
    from the slug (`manychat` -> "Manychat").

    Checks run one at a time (``_ashby_slot``). The read runs as its own
    task that holds the slot until it ends, including its JSON parse thread
    (a thread cannot be cancelled): when the 10 s budget (which also covers
    waiting for the slot) runs out, the user gets the error at once while
    the read finishes in the background, and only then may the next check
    start reading. So at most one Ashby parse thread runs at a time.

    Raises:
        BoardUnreadableError: unknown board (404), network error, timeout, an
            unexpected response, or the 10 s total budget ran out.
        SiteBlockedError: the API answered with a bot-protection challenge.
    """
    slot = _ashby_slot()
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
            await slot.acquire()
            # No await between acquiring and handing the slot to the task.
            read = asyncio.create_task(_read_ashby_board(org))
            read.add_done_callback(functools.partial(_release_ashby_slot, slot))
            # `asyncio.wait` never cancels `read` (unlike awaiting it), and,
            # unlike `asyncio.shield`, leaves no future whose late failure
            # asyncio would log: the done callback retrieves it.
            await asyncio.wait({read})
        read.result()  # re-raises the read's BoardReadError / TimeoutError
    except (TimeoutError, BoardReadError) as exc:
        logger.warning(
            "ashby_board_check_failed",
            org=org,
            error=getattr(exc, "reason", type(exc).__name__),
        )
        raise _board_check_error(exc) from exc
    return ashby.display_name(org)[:MAX_DISPLAY_NAME_LENGTH]


async def _read_ashby_board(org: str) -> None:
    """The read behind an Ashby check, with its own total limit.

    The limit (``ASHBY_READ_LIMIT_SECONDS``) keeps a slow answer from holding
    the slot for minutes. It is far above a real read (a 14 MB board takes
    about 1 s); should it cut a parse thread short, that thread still ends on
    its own, bounded by the 32 MB body cap.

    Raises:
        BoardReadError: see ``ashby.check_board``.
        TimeoutError: the read took longer than its limit.
    """
    async with (
        asyncio.timeout(ASHBY_READ_LIMIT_SECONDS),
        httpx.AsyncClient(timeout=CHECK_TIMEOUT_SECONDS) as client,
    ):
        await ashby.check_board(client, org)


def _release_ashby_slot(slot: asyncio.Semaphore, read: asyncio.Task[None]) -> None:
    """Free the slot when the read (and its parse thread) is over, and
    retrieve a late failure: the user was already told, nothing to log."""
    slot.release()
    if not read.cancelled():
        read.exception()


# --- web pages -----------------------------------------------------------------

PAGE_UNREADABLE_MESSAGE = "Could not open this page"
SITE_BLOCKED_MESSAGE = BLOCKED_MESSAGE
NO_VACANCIES_MESSAGE = (
    "No vacancies found on this page. Check the link or set 'Job link contains'."
)
# Preview reads page 1 only; saving reads up to web_scan.MAX_LISTING_PAGES.
PREVIEW_TIMEOUT_SECONDS = 15.0
SAVE_TIMEOUT_SECONDS = 45.0


class UnsafeLinkError(SourceCheckError):
    """The link (or a redirect) points to a local / private address or port."""

    message = UNSAFE_LINK_MESSAGE


class PageUnreadableError(SourceCheckError):
    """The first page did not open: network, timeout, HTTP error, not HTML."""

    message = PAGE_UNREADABLE_MESSAGE


class NoVacanciesError(SourceCheckError):
    """The first page opened but no job links were found on it."""

    message = NO_VACANCIES_MESSAGE


async def read_web_listing(
    url: str,
    job_link_contains: str | None,
    *,
    max_pages: int,
    total_timeout_s: float,
    allow_empty_with_hint: bool = False,
    stop_at_first_jobs: bool = False,
) -> web_scan.ListingRead:
    """Read the listing for the API; the result holds at least one job.

    With `allow_empty_with_hint` (preview only) a page 1 without jobs is still
    returned when it links to a job board, so the ATS hint can be shown.
    With `stop_at_first_jobs` (preview of a site-adapter link) reading stops
    after the first page that has jobs, so pages of only archived entries
    are skipped without reading the whole listing.

    Raises:
        UnsafeLinkError: the URL or a redirect on page 1 breaks the SSRF guard.
        PageUnreadableError: page 1 could not be read in time.
        SiteBlockedError: page 1 answered with a bot-protection challenge.
        NoVacanciesError: page 1 lists no jobs (and, with
            `allow_empty_with_hint`, links to no job board either).
    """
    try:
        listing = await web_scan.read_listing(
            url,
            job_link_contains,
            max_pages=max_pages,
            total_timeout_s=total_timeout_s,
            stop_after=(lambda jobs: True) if stop_at_first_jobs else None,
        )
    except UnsafeUrlError as exc:
        logger.info("web_page_check_refused")
        raise UnsafeLinkError from exc
    except PageFetchError as exc:
        logger.info("web_page_check_failed", reason=exc.reason)
        if exc.reason == "blocked":
            raise SiteBlockedError from exc
        raise PageUnreadableError from exc
    if not listing.jobs and not (
        allow_empty_with_hint and listing.ats_hint is not None
    ):
        raise NoVacanciesError
    return listing
