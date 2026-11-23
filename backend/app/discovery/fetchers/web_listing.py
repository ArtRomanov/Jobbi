"""Find job links and the next-page link on one job listing page.

Which ``<a href>`` counts as a job link:

- resolved against the page URL, normalized (``normalize_url``), ``http(s)``
  only; ``mailto:``/``tel:``/``javascript:`` and fragment-only links are skipped;
- on the page's host, one of its subdomains or its parent domain (``www.``
  is ignored when comparing);
- not the listing URL itself;
- with ``job_link_contains``: the URL contains that text (case-insensitive);
- without it: the path has a job-like segment (``job``, ``jobs``,
  ``vacanc*``, ``vakans*``, ``position(s)``, ``opening(s)``, ``career(s)``,
  ``role(s)``) followed by at least one more segment (an id or slug), e.g.
  ``/vacancy/123`` or ``/en/job/unity-dev``, but not ``/jobs`` or
  ``/jobs/vacancies``. Links to static files (``.png``, ``.css``, ...) are
  skipped. ``/job-<slug>``-style single segments are not recognized; such
  sites need ``job_link_contains``.

Anchors inside ``<nav>``/``<header>``/``<footer>`` or a pager (class/id
with ``paginat``/``pager``), with a filter-widget role
(``option``/``tab``/``menuitem``), or whose text is only digits (page
numbers) are not job links.

Next page: ``<link rel=next>`` / ``<a rel=next>``; else a link to the same
path whose ``page`` or ``p`` query value is the current one (default 1) + 1;
else a link whose last path segment is the next page number
(``/vacancies`` -> ``/vacancies/2``).

The title is the text of a heading (or ``*title*``-class element) inside the
anchor, else the anchor text, else its ``title``/``aria-label``. A link that
appears several times takes the first title marked up as one (heading or
``title``/``vacancy-name``-like class on the anchor or its parents), else the
first non-empty one. Links without any
title are dropped, unless a pattern was given (then the last path segment is
used).

ATS hint: every ``<a href>``, ``<iframe src>`` and ``<script src>`` on the
page, on any host, is run through ``parse_source_input``; Greenhouse, Lever
and Teamtailor boards count (Greenhouse embed links such as
``boards.greenhouse.io/embed/job_board?for=<token>`` give the ``for=`` token).
The board linked most often wins (ties: the first seen). Nothing is fetched.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from app.discovery.normalize import normalize_url
from app.services.vacancy_source_parsing import SourceInputError, parse_source_input

__all__ = ["AtsHint", "ListingJob", "ListingPage", "MAX_TITLE_CHARS", "parse_listing"]

MAX_TITLE_CHARS = 255

_JOB_SEGMENT_RE = re.compile(
    r"^(?:jobs?|vacanc\w*|vakans\w*|positions?|openings?|careers?|roles?)$",
    re.IGNORECASE,
)
_SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:")
_STATIC_SUFFIX_RE = re.compile(
    r"\.(?:png|jpe?g|gif|svg|webp|ico|css|js|json|xml|pdf|zip|woff2?|ttf|mp4)$",
    re.IGNORECASE,
)
_PAGE_PARAMS = ("page", "p")
_HEADINGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
_TITLE_CLASS_RE = re.compile(r"title|(?:vacanc\w*|job|position|role)[-_]?name", re.I)
# Anchors there are site navigation, not listings.
_CHROME_TAGS = ["nav", "header", "footer"]
_WIDGET_ROLES = frozenset({"option", "tab", "menuitem"})
_PAGER_RE = re.compile(r"paginat|pager", re.I)

# Board kind -> (service name, canonical link the add flow accepts).
_ATS_BOARDS: dict[str, tuple[str, str]] = {
    "greenhouse": ("Greenhouse", "https://job-boards.greenhouse.io/{handle}"),
    "lever": ("Lever", "https://jobs.lever.co/{handle}"),
    "lever_eu": ("Lever", "https://jobs.eu.lever.co/{handle}"),
    "teamtailor": ("Teamtailor", "https://{handle}.teamtailor.com"),
}
_ATS_HOST_SUFFIXES = (".greenhouse.io", ".lever.co", ".teamtailor.com")
_GREENHOUSE_EMBED_HOSTS = frozenset(
    {
        "boards.greenhouse.io",
        "job-boards.greenhouse.io",
        "boards.eu.greenhouse.io",
        "job-boards.eu.greenhouse.io",
    }
)
_GREENHOUSE_EMBED_PATH_RE = re.compile(r"/embed/(?:job_board(?:/js)?|job_app)/?")


@dataclass(frozen=True, slots=True)
class AtsHint:
    """A job board the page links to.

    ``input`` is a link the add flow accepts as that board; ``label`` is the
    service name shown to the user.
    """

    kind: str
    input: str
    label: str


@dataclass(frozen=True, slots=True)
class ListingJob:
    url: str
    title: str


@dataclass(frozen=True, slots=True)
class ListingPage:
    jobs: list[ListingJob] = field(default_factory=list)
    next_url: str | None = None
    ats_hint: AtsHint | None = None


def _bare_host(host: str) -> str:
    return host.removeprefix("www.")


def _same_site(host: str, page_host: str) -> bool:
    """``host`` is the page host, one of its subdomains or its parent domain."""
    link, page = _bare_host(host), _bare_host(page_host)
    if not link or not page:
        return False
    if link == page or link.endswith(f".{page}"):
        return True
    return "." in link and page.endswith(f".{link}")


def _resolve(href: str | None, page_url: str, page_host: str) -> str | None:
    """Absolute, normalized same-site http(s) URL of ``href``, or None."""
    if not href:
        return None
    raw = href.strip()
    if not raw or raw.startswith("#") or raw.lower().startswith(_SKIP_SCHEMES):
        return None
    url = normalize_url(urljoin(page_url, raw))
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    if not _same_site(parts.hostname, page_host):
        return None
    return url


def _segments(url: str) -> list[str]:
    return [unquote(s) for s in urlsplit(url).path.split("/") if s]


def _looks_like_job(url: str) -> bool:
    segments = _segments(url)
    if not segments or _STATIC_SUFFIX_RE.search(segments[-1]):
        return False
    job_positions = [i for i, s in enumerate(segments) if _JOB_SEGMENT_RE.match(s)]
    return bool(job_positions) and job_positions[-1] < len(segments) - 1


def _is_title_like(tag: Tag) -> bool:
    """A heading, or an element whose class names it a title."""
    if tag.name in _HEADINGS:
        return True
    classes = tag.get("class") or []
    return any(_TITLE_CLASS_RE.search(name) for name in classes)


def _text(tag: Tag) -> str:
    return " ".join(tag.get_text(" ").split())


def _anchor_title(anchor: Tag) -> tuple[str, bool]:
    """The anchor's title and whether it is marked up as a title.

    A heading / ``*title*``-class element inside the anchor wins over the
    whole anchor text (cards often wrap company, tags and date in one link).
    """
    inner = anchor.find(_HEADINGS) or anchor.find(_is_title_like)
    if isinstance(inner, Tag) and (title := _text(inner)):
        return title[:MAX_TITLE_CHARS], True
    title = _text(anchor)
    if not title:
        for attribute in ("title", "aria-label"):
            value = anchor.get(attribute)
            if isinstance(value, str) and value.strip():
                title = " ".join(value.split())
                break
    is_marked = any(
        isinstance(tag, Tag) and _is_title_like(tag)
        for tag in (anchor, anchor.parent, getattr(anchor.parent, "parent", None))
    )
    return title[:MAX_TITLE_CHARS], is_marked and bool(title)


def _is_pager(tag: Tag) -> bool:
    names = [*(tag.get("class") or []), str(tag.get("id") or "")]
    return any(_PAGER_RE.search(name) for name in names)


def _in_page_chrome(anchor: Tag) -> bool:
    """Inside navigation / header / footer / a pager, or a filter widget."""
    if str(anchor.get("role") or "").lower() in _WIDGET_ROLES:
        return True
    if anchor.find_parent(_CHROME_TAGS) is not None:
        return True
    return _is_pager(anchor) or anchor.find_parent(_is_pager) is not None


def _has_rel_next(tag: Tag) -> bool:
    rel = tag.get("rel")
    values = rel if isinstance(rel, list) else str(rel or "").split()
    return any(value.lower() == "next" for value in values)


def _find_next(
    soup: BeautifulSoup, anchors: list[Tag], page_url: str, page_host: str
) -> str | None:
    for tag in soup.find_all(["link", "a"]):
        if isinstance(tag, Tag) and _has_rel_next(tag):
            url = _resolve(_attr(tag, "href"), page_url, page_host)
            if url and url != page_url:
                return url

    page_parts = urlsplit(page_url)
    page_query = dict(parse_qsl(page_parts.query))
    for name in _PAGE_PARAMS:
        current = page_query.get(name, "1")
        if not current.isdigit():
            continue
        wanted = str(int(current) + 1)
        for anchor in anchors:
            url = _resolve(_attr(anchor, "href"), page_url, page_host)
            if not url:
                continue
            parts = urlsplit(url)
            if (parts.hostname, parts.path) != (page_parts.hostname, page_parts.path):
                continue
            if dict(parse_qsl(parts.query)).get(name) == wanted:
                return url

    # Page number as the last path segment: /vacancies -> /vacancies/2,
    # /vacancies/2 -> /vacancies/3.
    segments = [s for s in page_parts.path.split("/") if s]
    base = _page_base(page_parts.path)
    wanted = str(int(segments[-1]) + 1) if len(base) < len(segments) else "2"
    wanted_path = "/" + "/".join([*base, wanted])
    for anchor in anchors:
        url = _resolve(_attr(anchor, "href"), page_url, page_host)
        if url:
            parts = urlsplit(url)
            if (parts.hostname, parts.path) == (page_parts.hostname, wanted_path):
                return url
    return None


def _page_base(path: str) -> list[str]:
    """Path segments of a listing URL without a trailing page number."""
    segments = [s for s in path.split("/") if s]
    return segments[:-1] if segments and segments[-1].isdigit() else segments


def _attr(tag: Tag, name: str) -> str | None:
    value = tag.get(name)
    return value if isinstance(value, str) else None


def _board_of(raw: str | None, page_url: str) -> tuple[str, str] | None:
    """``(kind, handle)`` of a Greenhouse/Lever/Teamtailor board link, or None."""
    if not raw or not (raw := raw.strip()):
        return None
    try:
        parts = urlsplit(urljoin(page_url, raw))
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not f".{host}".endswith(
        _ATS_HOST_SUFFIXES
    ):
        return None
    if host in _GREENHOUSE_EMBED_HOSTS and _GREENHOUSE_EMBED_PATH_RE.fullmatch(
        parts.path
    ):
        # The board pattern rejects `/embed/...`; the token is in `for=`.
        # Checking the canonical board link keeps the token as strict as a
        # pasted one (charset, length, reserved words).
        token = dict(parse_qsl(parts.query)).get("for", "")
        if not token or "/" in token or "?" in token or "#" in token:
            return None
        link = _ATS_BOARDS["greenhouse"][1].format(handle=token)
    else:
        # The fragment is page-local; board patterns do not accept it.
        link = parts._replace(fragment="").geturl()
    try:
        parsed = parse_source_input(link)
    except SourceInputError:
        return None
    if parsed.kind not in _ATS_BOARDS:
        return None
    return parsed.kind, parsed.handle


def _find_ats_hint(soup: BeautifulSoup, page_url: str) -> AtsHint | None:
    counts: Counter[tuple[str, str]] = Counter()
    for tag in soup.find_all(["a", "iframe", "script"]):
        if not isinstance(tag, Tag):
            continue
        attribute = "href" if tag.name == "a" else "src"
        if (board := _board_of(_attr(tag, attribute), page_url)) is not None:
            counts[board] += 1
    if not counts:
        return None
    # Counter keeps first-seen order and max() returns the first maximum.
    kind, handle = max(counts, key=counts.__getitem__)
    label, template = _ATS_BOARDS[kind]
    return AtsHint(kind=kind, input=template.format(handle=handle), label=label)


def parse_listing(
    html: str, page_url: str, job_link_contains: str | None
) -> ListingPage:
    """Job links (page order, deduped by normalized URL), the next page URL and
    the job board the page links to most (see the module docstring).

    ``page_url`` is the URL the page was fetched from (after redirects).
    """
    page_url = normalize_url(page_url)
    page_host = (urlsplit(page_url).hostname or "").lower()
    pattern = (job_link_contains or "").strip().lower() or None
    soup = BeautifulSoup(html, "html.parser")
    anchors = [a for a in soup.find_all("a", href=True) if isinstance(a, Tag)]

    found: dict[str, tuple[str, bool]] = {}  # url -> (title, is_marked)
    for anchor in anchors:
        if _in_page_chrome(anchor):
            continue
        url = _resolve(_attr(anchor, "href"), page_url, page_host)
        if url is None or url == page_url:
            continue
        if pattern is not None:
            if pattern not in url.lower():
                continue
        elif not _looks_like_job(url):
            continue
        title, is_marked = _anchor_title(anchor)
        if title.isdigit():
            continue  # a page number such as /vacancies/2
        known_title, known_marked = found.get(url, ("", False))
        if (not known_title and title) or (is_marked and not known_marked):
            found[url] = (title, is_marked)
        else:
            found.setdefault(url, (title, is_marked))

    jobs: list[ListingJob] = []
    for url, (title, _) in found.items():
        if not title:
            if pattern is None:
                continue
            segments = _segments(url)
            title = (segments[-1] if segments else url)[:MAX_TITLE_CHARS]
        jobs.append(ListingJob(url=url, title=title))

    return ListingPage(
        jobs=jobs,
        next_url=_find_next(soup, anchors, page_url, page_host),
        ats_hint=_find_ats_hint(soup, page_url),
    )
