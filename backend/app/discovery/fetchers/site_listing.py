"""Site listing adapters: sites whose search results come from their own JSON.

Some listing pages are an empty HTML shell; the site's JavaScript loads the
results from a JSON endpoint. For a known site, ``find_site_listing`` turns
the pasted search link into a ``SiteListing`` that names the JSON URL of
each results page and maps one JSON answer to a ``ListingPage`` (the same
type the HTML parser returns). ``web_scan.read_listing`` then reads that
endpoint instead of the HTML page; everything after the listing (seen keys,
the job-page detail step, AI) is unchanged. Every other link
keeps the generic HTML path.

The JSON is requested through ``safe_http.fetch_json`` like any user-chosen
URL. Parsing never raises: an unexpected shape gives an empty page.

geekjob.ru (``geekjob.ru`` / ``www.geekjob.ru``, path ``/vacancies`` or
``/vacancies/<page>``): ``/app/filters/vacancies/app.js`` reads the filters
from the page URL and calls ``GET /json/find/vacancy?page=N&<filters>``,
which answers ``{page, nextpage, pagecount, documentsCount, data: [{id,
position, company, log: {modify, archived}, ...}]}`` (up to 100 per page;
``nextpage`` is 0 on the last page). Only the filters the site's script
itself reads from the page URL are copied: ``qs`` (search text), ``t``
(comma-separated tag ids), ``s`` (salary given; the script then always sends
its own ``money=120000``, never one from the URL), ``pt``, ``ih``, ``rm``,
``rl``, ``na`` (part-time, in-house, remote, relocation, no agencies).
``or``, ``money`` and ``f`` in the pasted link are ignored, as on the site.
At least one filter is needed, otherwise the page is server-rendered and
read as HTML. A single trailing dot on the host (``geekjob.ru.``) is allowed. ``sort=1`` ("by date", newest first) is always sent, so the
worker's "stop at the first page with a seen job" rule holds. A job is
``https://geekjob.ru/vacancy/<id>`` titled by ``position``; archived jobs
are skipped.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

import structlog

from app.discovery.fetchers.safe_http import PageFetchError
from app.discovery.fetchers.web_listing import MAX_TITLE_CHARS, ListingJob, ListingPage
from app.discovery.normalize import normalize_url, strip_invisible

__all__ = [
    "MAX_ITEMS_PER_PAGE",
    "MAX_QUERY_CHARS",
    "SiteListing",
    "find_site_listing",
]

logger = structlog.get_logger()

# A real answer has at most 100 items.
MAX_ITEMS_PER_PAGE = 200
MAX_QUERY_CHARS = 200

PageParser = Callable[["SiteListing", Any, int, str | None], ListingPage]


@dataclass(frozen=True, slots=True)
class SiteListing:
    """A search on a site read through its JSON endpoint.

    ``params`` are the filters sent with every page (without ``page``).
    ``canonical_url`` is the one listing URL for every spelling of the same
    search (only the filters the adapter sends, apex host): the source is
    stored and de-duplicated by it. The JSON endpoint is on a fixed host, so
    its requests follow no redirects (``max_redirects``).
    """

    name: str
    api_url: str
    params: tuple[tuple[str, str], ...]
    parser: PageParser
    canonical_url: str
    max_redirects: int = 0

    def page_url(self, page: int) -> str:
        """The JSON URL of results page ``page`` (1-based)."""
        query = urlencode(
            [("page", str(page)), *self.params], safe=",", quote_via=quote
        )
        return f"{self.api_url}?{query}"

    def parse_page(
        self, data: Any, page: int, job_link_contains: str | None
    ) -> ListingPage:
        """Jobs of one JSON answer, how many entries it had, and the next page.

        ``job_link_contains`` keeps only job URLs containing it
        (case-insensitive), as on HTML listings. An unexpected shape gives an
        empty page. CPU work on remote input: async callers run it through
        ``asyncio.to_thread``.

        Raises:
            PageFetchError: ``unreachable`` if the parser itself fails (a bug
                on odd input): the page reads as "could not open", not as
                "no vacancies". Nothing else is raised.
        """
        try:
            return self.parser(self, data, page, job_link_contains)
        except Exception as exc:  # a parser bug on remote JSON: page unreadable
            logger.warning(
                "site_listing_parse_failed", site=self.name, error=type(exc).__name__
            )
            raise PageFetchError("unreachable") from exc


# --- geekjob.ru ---------------------------------------------------------------------

_GEEKJOB_HOSTS = frozenset({"geekjob.ru", "www.geekjob.ru"})
_GEEKJOB_PATH_RE = re.compile(r"/vacancies(?:/\d{1,4})?/?", re.ASCII)
_GEEKJOB_API = "https://geekjob.ru/json/find/vacancy"
_GEEKJOB_LISTING = "https://geekjob.ru/vacancies"
_GEEKJOB_JOB_URL = "https://geekjob.ru/vacancy/{id}"
_GEEKJOB_FLAGS = ("pt", "ih", "rm", "rl", "na")
_GEEKJOB_DEFAULT_MONEY = "120000"
_GEEKJOB_NEWEST_FIRST = ("sort", "1")
_TAG_LIST_RE = re.compile(r"\d{1,6}(?:,\d{1,6}){0,49}", re.ASCII)
_ITEM_ID_RE = re.compile(r"[A-Za-z0-9]{1,64}", re.ASCII)


def _geekjob_params(query: str) -> list[tuple[str, str]]:
    """The recognised filters of a pasted search link, in a fixed order."""
    values: dict[str, str] = {}
    for name, value in parse_qsl(query):
        values.setdefault(name, value)
    params: list[tuple[str, str]] = []
    text = values.get("qs", "").strip()[:MAX_QUERY_CHARS].strip()
    if text:
        params.append(("qs", text))
    if _TAG_LIST_RE.fullmatch(values.get("t", "")):
        params.append(("t", values["t"]))
    if values.get("s"):
        params.append(("s", "1"))
        params.append(("money", _GEEKJOB_DEFAULT_MONEY))
    params.extend((flag, "1") for flag in _GEEKJOB_FLAGS if values.get(flag))
    return params


def _host_without_root_dot(hostname: str | None) -> str:
    """Lowercased host with one trailing (DNS root) dot removed."""
    host = (hostname or "").lower()
    return host.removesuffix(".")


def _match_geekjob(url: str) -> SiteListing | None:
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        return None
    if (
        parts.scheme.lower() not in ("http", "https")
        or parts.username is not None
        or parts.password is not None
        or port is not None
        or _host_without_root_dot(parts.hostname) not in _GEEKJOB_HOSTS
        or not _GEEKJOB_PATH_RE.fullmatch(parts.path)
    ):
        return None
    params = _geekjob_params(parts.query)
    if not params:
        return None
    # `money` follows from `s` (the script's fixed amount), so it is left out.
    filters = [(name, value) for name, value in params if name != "money"]
    return SiteListing(
        name="geekjob",
        api_url=_GEEKJOB_API,
        params=(*params, _GEEKJOB_NEWEST_FIRST),
        parser=_geekjob_page,
        canonical_url=normalize_url(f"{_GEEKJOB_LISTING}?{urlencode(filters)}"),
    )


def _clean_title(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    visible = strip_invisible(value[: MAX_TITLE_CHARS * 4])
    title = " ".join(visible.split())[:MAX_TITLE_CHARS]
    return title or None


def _is_archived(item: dict[str, Any]) -> bool:
    log = item.get("log")
    if log is None:
        return False
    # An unexpected shape is not trusted to be an open job.
    return not isinstance(log, dict) or bool(log.get("archived"))


@dataclass(frozen=True, slots=True)
class _GeekjobItems:
    jobs: list[ListingJob]
    # Entries that were valid open jobs before `job_link_contains` was applied.
    usable: int
    # Entries dropped as archived or invalid.
    skipped: int


def _geekjob_jobs(data: Any, job_link_contains: str | None) -> _GeekjobItems:
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        return _GeekjobItems(jobs=[], usable=0, skipped=0)
    pattern = job_link_contains.lower() if job_link_contains else None
    jobs: list[ListingJob] = []
    seen: set[str] = set()
    usable = skipped = 0
    for item in data["data"][:MAX_ITEMS_PER_PAGE]:
        if not isinstance(item, dict) or _is_archived(item):
            skipped += 1
            continue
        item_id = item.get("id")
        title = _clean_title(item.get("position"))
        if (
            not isinstance(item_id, str)
            or not _ITEM_ID_RE.fullmatch(item_id)
            or title is None
        ):
            skipped += 1
            continue
        usable += 1
        url = _GEEKJOB_JOB_URL.format(id=item_id)
        if url in seen or (pattern is not None and pattern not in url.lower()):
            continue
        seen.add(url)
        jobs.append(ListingJob(url=url, title=title))
    return _GeekjobItems(jobs=jobs, usable=usable, skipped=skipped)


def _geekjob_next(listing: SiteListing, data: Any, page: int) -> str | None:
    if not isinstance(data, dict):
        return None
    nextpage = data.get("nextpage")
    if isinstance(nextpage, bool) or not isinstance(nextpage, int):
        return None
    return listing.page_url(page + 1) if nextpage > page else None


def _geekjob_page(
    listing: SiteListing, data: Any, page: int, job_link_contains: str | None
) -> ListingPage:
    items = _geekjob_jobs(data, job_link_contains)
    # Only a page whose entries were all archived/invalid continues the
    # listing; usable jobs filtered out by the pattern end it as usual.
    return ListingPage(
        jobs=items.jobs,
        next_url=_geekjob_next(listing, data, page),
        skipped_count=items.skipped if items.usable == 0 else 0,
    )


# --- registry -------------------------------------------------------------------------

_MATCHERS: tuple[Callable[[str], SiteListing | None], ...] = (_match_geekjob,)


def find_site_listing(url: str) -> SiteListing | None:
    """The JSON adapter for a listing URL, or None to read it as HTML."""
    for matcher in _MATCHERS:
        listing = matcher(url)
        if listing is not None:
            return listing
    return None
