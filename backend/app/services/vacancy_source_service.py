"""Watched sources (Telegram channels, Greenhouse / Lever / Teamtailor / Ashby
boards, web listing pages).

Invariant: no network I/O inside a database transaction. `add_source` and
`preview_source` end the read transaction before the live check; `add_source`
writes in a short one after.
"""

import hashlib
import uuid
from collections.abc import Collection
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import Enum
from urllib.parse import urlsplit

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.discovery.fetchers.site_listing import find_site_listing
from app.discovery.fetchers.web_listing import AtsHint, ListingJob
from app.discovery.web_scan import MAX_LISTING_PAGES, web_seen_key
from app.models.vacancy import Vacancy, VacancyCardSource
from app.models.vacancy_search_settings import VacancySearchSettings
from app.models.vacancy_seen_key import VacancySeenKey
from app.models.vacancy_source import VacancySource
from app.services.vacancy_source_check import (
    PREVIEW_TIMEOUT_SECONDS,
    SAVE_TIMEOUT_SECONDS,
    check_ashby_board,
    check_lever_board,
    fetch_greenhouse_board_name,
    fetch_teamtailor_board_name,
    fetch_telegram_channel_title,
    read_web_listing,
)
from app.services.vacancy_source_parsing import (
    ParsedSource,
    SourceInputError,
    parse_source_input,
)

MAX_SOURCES = 30
UNAVAILABLE_AFTER = timedelta(hours=24)
# A first-scan lease older than this belongs to a crashed worker.
ATTEMPT_LEASE_TTL = timedelta(minutes=10)
MAX_SOURCE_NAME_LENGTH = 100
MAX_JOB_LINK_CONTAINS_LENGTH = 100
PREVIEW_TITLES = 5

SOURCE_LIMIT_MESSAGE = "You can watch up to 30 sources"
DUPLICATE_SOURCE_MESSAGE = "Already in your sources"
NAME_TOO_LONG_MESSAGE = "Name can be up to 100 characters"
BAD_JOB_LINK_CONTAINS_MESSAGE = "'Job link contains' must be 1–100 characters"
SOURCE_BUSY_MESSAGE = "This source is being scanned — try again in a moment"

MAX_DESCRIPTION_LENGTH = 500

DESCRIPTION_TOO_LONG_MESSAGE = "Description can be up to 500 characters"

MAX_KEYWORDS = 50
MAX_KEYWORD_LENGTH = 64

TOO_MANY_KEYWORDS_MESSAGE = "You can add up to 50 keywords"
BAD_KEYWORD_MESSAGE = "Keywords must be 1–64 characters"
KEYWORD_WITHOUT_LETTERS_MESSAGE = "Keywords must contain a letter or a digit"


class _Unset(Enum):
    UNSET = "unset"


UNSET = _Unset.UNSET


class SourceLimitError(Exception):
    """The user already watches MAX_SOURCES sources."""


class DuplicateSourceError(Exception):
    """The same kind + handle (web: the same normalized URL) is already watched."""


class SourceNotFoundError(Exception):
    """The given source id is not one of the user's sources."""


class SourceBusyError(Exception):
    """A first-scan attempt is running (fresh lease), so the source cannot be
    edited right now."""


@dataclass(frozen=True, slots=True)
class SourcePreview:
    """What `preview_source` found; only `kind` is set for non-web sources."""

    kind: str
    default_name: str | None = None
    found_count: int | None = None
    titles: list[str] | None = None
    ats_hint: AtsHint | None = None


class SearchSettingsError(Exception):
    """A search setting is outside its limits; `message` is user-facing."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def is_scanning(source: VacancySource) -> bool:
    return source.initial_scan_completed_at is None


def is_attempt_running(source: VacancySource, now: datetime | None = None) -> bool:
    """True while the worker's first-scan lease is fresh (a crashed worker's
    lease is ignored after ATTEMPT_LEASE_TTL)."""
    started = source.initial_attempt_started_at
    if started is None:
        return False
    return (now or _now_naive()) - started < ATTEMPT_LEASE_TTL


def is_unavailable(source: VacancySource, now: datetime | None = None) -> bool:
    if source.failing_since is None:
        return False
    return (now or _now_naive()) - source.failing_since >= UNAVAILABLE_AFTER


async def list_sources(db: AsyncSession, user_id: str) -> list[VacancySource]:
    result = await db.execute(
        select(VacancySource)
        .where(VacancySource.user_id == user_id)
        .order_by(VacancySource.created_at, VacancySource.id)
    )
    return list(result.scalars().all())


async def pending_counts(
    db: AsyncSession, user_id: str, source_ids: Collection[str] | None = None
) -> dict[str, int]:
    """Pending posts per source ("Waiting for AI: N"), one grouped COUNT.

    Same rule as the Inbox banner (`vacancy_service._count_waiting`): web rows
    whose job page is not read yet (`needs_detail`) wait for the page reader,
    not the AI, so they don't count. Forwarded posts have no source and are
    not counted. Sources with nothing pending are absent.
    `source_ids` narrows the query (one edited source).
    """
    stmt = (
        select(Vacancy.source_id, func.count())
        .where(
            Vacancy.user_id == user_id,
            Vacancy.state == "pending",
            Vacancy.needs_detail.is_(False),
            Vacancy.source_id.is_not(None),
        )
        .group_by(Vacancy.source_id)
    )
    if source_ids is not None:
        stmt = stmt.where(Vacancy.source_id.in_(list(source_ids)))
    rows = await db.execute(stmt)
    return {source_id: count for source_id, count in rows}


async def get_search_settings(
    db: AsyncSession, user_id: str
) -> VacancySearchSettings | None:
    result = await db.execute(
        select(VacancySearchSettings).where(VacancySearchSettings.user_id == user_id)
    )
    return result.scalar_one_or_none()


def normalize_description(raw: str | None) -> str | None:
    """Trim; blank means "search off" (None).

    Raises:
        SearchSettingsError: longer than MAX_DESCRIPTION_LENGTH after trimming.
    """
    if raw is None:
        return None
    description = raw.strip()
    if not description:
        return None
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise SearchSettingsError(DESCRIPTION_TOO_LONG_MESSAGE)
    return description


def normalize_keywords(raw: list[str]) -> list[str]:
    """Trim, collapse inner whitespace, lowercase, de-duplicate keeping order.

    Stops at the first problem, and as soon as a 51st unique keyword appears
    (the raw list is bounded by the schema too).

    Raises:
        SearchSettingsError: a keyword is empty, too long or has no letter or
            digit, or there are more than MAX_KEYWORDS unique keywords.
    """
    keywords: dict[str, None] = {}  # insertion-ordered set
    for item in raw:
        keyword = " ".join(item.split()).lower()
        if not keyword or len(keyword) > MAX_KEYWORD_LENGTH:
            raise SearchSettingsError(BAD_KEYWORD_MESSAGE)
        if not any(char.isalnum() for char in keyword):
            raise SearchSettingsError(KEYWORD_WITHOUT_LETTERS_MESSAGE)
        keywords[keyword] = None
        if len(keywords) > MAX_KEYWORDS:
            raise SearchSettingsError(TOO_MANY_KEYWORDS_MESSAGE)
    return list(keywords)


async def update_search_settings(
    db: AsyncSession,
    user_id: str,
    *,
    description: str | None | _Unset = UNSET,
    keywords: list[str] | _Unset = UNSET,
    keyword_filter_enabled: bool | _Unset = UNSET,
) -> VacancySearchSettings:
    """Partially update the user's settings, creating the row on first use.

    Arguments left as UNSET keep their stored value.

    Raises:
        SearchSettingsError: a value is outside its limits (nothing is saved).
    """
    # Validate everything before touching the database.
    new_description = (
        UNSET if isinstance(description, _Unset) else normalize_description(description)
    )
    new_keywords = (
        UNSET if isinstance(keywords, _Unset) else normalize_keywords(keywords)
    )

    # Two attempts: a concurrent first PATCH may insert the row between our
    # SELECT and INSERT; the primary key rejects ours and we update theirs.
    for attempt in range(2):
        settings_row = await get_search_settings(db, user_id)
        if settings_row is None:
            settings_row = VacancySearchSettings(user_id=user_id)
            db.add(settings_row)
        if not isinstance(new_description, _Unset):
            settings_row.description = new_description
        if not isinstance(new_keywords, _Unset):
            # A new list object, so the JSON column change is detected.
            settings_row.keywords = list(new_keywords)
        if not isinstance(keyword_filter_enabled, _Unset):
            settings_row.keyword_filter_enabled = keyword_filter_enabled
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            if attempt == 1:
                raise
            continue
        await db.refresh(settings_row)
        return settings_row
    raise AssertionError("unreachable")  # pragma: no cover


def canonical_web_url(url: str) -> str:
    """The URL a web source is stored and de-duplicated by.

    For a link a site listing adapter reads (a geekjob.ru search) it is the
    adapter's canonical URL, so every spelling of one search (``www.``,
    ``/vacancies/<n>``, parameters the site ignores, a repeated ``qs``) is one
    source; any other link stays as normalized by the parser. Sources stored
    before this rule keep their URL and hash (no migration): they are still
    read correctly, an edit to an equivalent spelling is a no-op, but a new
    add of the same search in canonical form is not matched against them.
    """
    listing = find_site_listing(url)
    return url if listing is None else listing.canonical_url


def parse_input(raw: str) -> ParsedSource:
    """``parse_source_input`` with the web URL made canonical.

    Raises:
        SourceInputError: see ``parse_source_input``.
    """
    parsed = parse_source_input(raw)
    if parsed.kind != "web" or parsed.url is None:
        return parsed
    return replace(parsed, url=canonical_web_url(parsed.url))


def url_hash(url: str) -> str:
    """sha256 hex of an already normalized URL (backs the duplicate check)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def web_default_name(url: str) -> str:
    """The listing's host without a leading `www.` (e.g. "geekjob.ru")."""
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.") or url


def normalize_source_name(raw: str | None) -> str | None:
    """Trim; blank means "use the default name" (None).

    Raises:
        SourceInputError: longer than MAX_SOURCE_NAME_LENGTH after trimming.
    """
    name = (raw or "").strip()
    if not name:
        return None
    if len(name) > MAX_SOURCE_NAME_LENGTH:
        raise SourceInputError(NAME_TOO_LONG_MESSAGE)
    return name


def normalize_job_link_contains(raw: str | None) -> str | None:
    """Trim; blank means "pick job links automatically" (None).

    Raises:
        SourceInputError: longer than MAX_JOB_LINK_CONTAINS_LENGTH after
            trimming, or contains control characters.
    """
    pattern = (raw or "").strip()
    if not pattern:
        return None
    if len(pattern) > MAX_JOB_LINK_CONTAINS_LENGTH or not pattern.isprintable():
        raise SourceInputError(BAD_JOB_LINK_CONTAINS_MESSAGE)
    return pattern


async def _source_exists(
    db: AsyncSession,
    user_id: str,
    parsed: ParsedSource,
    exclude_id: str | None = None,
) -> bool:
    stmt = select(VacancySource.id).where(VacancySource.user_id == user_id)
    if parsed.kind == "web":
        assert parsed.url is not None
        stmt = stmt.where(VacancySource.url_hash == url_hash(parsed.url))
    else:
        stmt = stmt.where(
            VacancySource.kind == parsed.kind,
            VacancySource.handle == parsed.handle,
        )
    if exclude_id is not None:
        stmt = stmt.where(VacancySource.id != exclude_id)
    result = await db.execute(stmt.limit(1))
    return result.first() is not None


async def _count_sources(
    db: AsyncSession, user_id: str, exclude_id: str | None = None
) -> int:
    stmt = (
        select(func.count())
        .select_from(VacancySource)
        .where(VacancySource.user_id == user_id)
    )
    if exclude_id is not None:
        stmt = stmt.where(VacancySource.id != exclude_id)
    result = await db.execute(stmt)
    return result.scalar_one()


async def _check_can_add(
    db: AsyncSession,
    user_id: str,
    parsed: ParsedSource,
    exclude_id: str | None = None,
) -> None:
    if await _source_exists(db, user_id, parsed, exclude_id):
        raise DuplicateSourceError
    if await _count_sources(db, user_id, exclude_id) >= MAX_SOURCES:
        raise SourceLimitError


async def _check_owned(db: AsyncSession, user_id: str, source_id: str) -> None:
    result = await db.execute(
        select(VacancySource.id).where(
            VacancySource.id == source_id, VacancySource.user_id == user_id
        )
    )
    if result.first() is None:
        raise SourceNotFoundError


async def preview_source(
    db: AsyncSession,
    user_id: str,
    raw_input: str,
    *,
    job_link_contains: str | None = None,
    source_id: str | None = None,
) -> SourcePreview:
    """Show what a source would be, without saving anything.

    Non-web kinds: only the parsed kind, no network call and no checks (the
    create call does those). Web: duplicate and limit checks (`source_id`, the
    source being edited, is left out of both), then page 1 of the listing.

    Raises:
        SourceInputError: unrecognised input or a bad `job_link_contains`.
        SourceNotFoundError: `source_id` is not one of the user's sources.
        DuplicateSourceError: the same normalized URL is already watched.
        SourceLimitError: MAX_SOURCES reached.
        SourceCheckError: unsafe link, page not readable, or no vacancies
            and no job board link (no vacancies + a board link is a 200 with
            `found_count` 0 and the `ats_hint`).
    """
    parsed = parse_input(raw_input)
    if parsed.kind != "web":
        return SourcePreview(kind=parsed.kind)
    assert parsed.url is not None
    pattern = normalize_job_link_contains(job_link_contains)

    if source_id is not None:
        await _check_owned(db, user_id, source_id)
    await _check_can_add(db, user_id, parsed, exclude_id=source_id)
    # End the read transaction before going to the network (see add_source).
    await db.commit()

    # An HTML page previews page 1 only. A site-adapter link (geekjob search)
    # may start with pages of only archived entries: read on to the first
    # page with jobs (up to MAX_LISTING_PAGES, same preview time budget).
    is_adapter = find_site_listing(parsed.url) is not None
    listing = await read_web_listing(
        parsed.url,
        pattern,
        max_pages=MAX_LISTING_PAGES if is_adapter else 1,
        total_timeout_s=PREVIEW_TIMEOUT_SECONDS,
        allow_empty_with_hint=True,
        stop_at_first_jobs=is_adapter,
    )
    return SourcePreview(
        kind=parsed.kind,
        default_name=web_default_name(parsed.url),
        found_count=len(listing.jobs),
        titles=[job.title for job in listing.jobs[:PREVIEW_TITLES]],
        ats_hint=listing.ats_hint,
    )


async def _fetch_display_name(parsed: ParsedSource) -> str:
    match parsed.kind:
        case "telegram":
            return await fetch_telegram_channel_title(parsed.handle)
        case "greenhouse":
            return await fetch_greenhouse_board_name(parsed.handle)
        case "lever" | "lever_eu":
            return await check_lever_board(parsed.kind, parsed.handle)
        case "teamtailor":
            return await fetch_teamtailor_board_name(parsed.handle)
        case "ashby":
            return await check_ashby_board(parsed.handle)
        case _:  # pragma: no cover - the parser yields only the kinds above
            raise NotImplementedError(parsed.kind)


async def add_source(
    db: AsyncSession,
    user_id: str,
    raw_input: str,
    *,
    job_link_contains: str | None = None,
    name: str | None = None,
) -> VacancySource:
    """Parse, check limits and duplicates, verify live, then save.

    `job_link_contains` and `name` apply to web pages only; for other kinds
    `name` is validated but not applied yet (renaming comes with Edit).

    Raises:
        SourceInputError: unrecognised input, or a bad name / pattern.
        DuplicateSourceError: already watched (checked before and after the
            live check; the unique constraint closes the race).
        SourceLimitError: MAX_SOURCES reached.
        SourceCheckError: the live check failed (channel not public, board
            unreadable, unreachable; web: unsafe link, page not readable or
            no vacancies on page 1).
    """
    parsed = parse_input(raw_input)
    custom_name = normalize_source_name(name)
    if parsed.kind == "web":
        pattern = normalize_job_link_contains(job_link_contains)
        return await _add_web_source(db, user_id, parsed, pattern, custom_name)

    # Cheap checks first, so a duplicate or a full list costs no network call.
    await _check_can_add(db, user_id, parsed)
    # End the read transaction before going to the network. commit (not
    # rollback) so already-loaded objects such as the current user are not
    # expired; nothing has been written, so it is a no-op otherwise.
    await db.commit()

    display_name = await _fetch_display_name(parsed)

    # Re-check: another request may have added sources while we were waiting.
    await _check_can_add(db, user_id, parsed)
    source = VacancySource(
        user_id=user_id,
        kind=parsed.kind,
        handle=parsed.handle,
        default_name=display_name,
        display_name=display_name,
    )
    db.add(source)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateSourceError from exc
    await db.refresh(source)
    return source


async def _add_web_source(
    db: AsyncSession,
    user_id: str,
    parsed: ParsedSource,
    pattern: str | None,
    custom_name: str | None,
) -> VacancySource:
    """Read the listing (up to MAX_LISTING_PAGES pages), then save the source
    with every listed job remembered as seen, in one short transaction.

    The first scan is complete at once: only jobs that appear later are new.
    """
    assert parsed.url is not None
    await _check_can_add(db, user_id, parsed)
    await db.commit()  # no transaction open during the fetch

    listing = await read_web_listing(
        parsed.url,
        pattern,
        max_pages=MAX_LISTING_PAGES,
        total_timeout_s=SAVE_TIMEOUT_SECONDS,
    )

    await _check_can_add(db, user_id, parsed)
    source = _build_web_source(user_id, parsed, pattern, custom_name)
    db.add(source)
    db.add_all(_seen_keys(user_id, source.id, listing.jobs))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateSourceError from exc
    await db.refresh(source)
    return source


def _build_web_source(
    user_id: str,
    parsed: ParsedSource,
    pattern: str | None,
    custom_name: str | None,
) -> VacancySource:
    """A new web source whose first scan is already complete (the listing
    read before saving counts as it)."""
    assert parsed.url is not None
    now = _now_naive()
    source_id = str(uuid.uuid4())
    default_name = web_default_name(parsed.url)
    return VacancySource(
        id=source_id,
        user_id=user_id,
        kind="web",
        handle=source_id,
        url=parsed.url,
        url_hash=url_hash(parsed.url),
        job_link_contains=pattern,
        default_name=default_name,
        display_name=custom_name or default_name,
        initial_scan_completed_at=now,
        last_checked_at=now,
    )


def _seen_keys(
    user_id: str, source_id: str, jobs: list[ListingJob]
) -> list[VacancySeenKey]:
    keys = dict.fromkeys(web_seen_key(source_id, job.url) for job in jobs)
    return [VacancySeenKey(user_id=user_id, external_key=key) for key in keys]


async def _get_owned_source(
    db: AsyncSession, user_id: str, source_id: str
) -> VacancySource:
    """The user's source with its current column values.

    `populate_existing` overwrites an object already in the session: sessions
    keep objects after commit (`expire_on_commit=False`), so a plain re-select
    after a network call would return the values read before it and miss a
    lease, rename or edit saved meanwhile.
    """
    result = await db.execute(
        select(VacancySource)
        .where(VacancySource.id == source_id, VacancySource.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    source = result.scalar_one_or_none()
    if source is None:
        await db.rollback()
        raise SourceNotFoundError
    return source


def _custom_name(source: VacancySource) -> str | None:
    """The user's own name for the source, None when it shows the default."""
    if source.display_name == source.default_name:
        return None
    return source.display_name


async def rename_source(
    db: AsyncSession,
    user_id: str,
    source_id: str,
    name: str | None | _Unset = UNSET,
) -> VacancySource:
    """Set the source's display name; null or blank restores the default name,
    UNSET leaves it unchanged (the source is still looked up).

    No network call: the name is the user's own label. Live card labels follow
    at once (the Inbox reads the live name).

    Raises:
        SourceInputError: the name is longer than MAX_SOURCE_NAME_LENGTH.
        SourceNotFoundError: not one of the user's sources.
        SourceBusyError: a first-scan attempt is running.
    """
    custom_name = None if isinstance(name, _Unset) else normalize_source_name(name)
    source = await _get_owned_source(db, user_id, source_id)
    if is_attempt_running(source):
        await db.rollback()
        raise SourceBusyError
    if not isinstance(name, _Unset):
        source.display_name = custom_name or source.default_name
    await db.commit()
    await db.refresh(source)
    return source


async def edit_source(
    db: AsyncSession,
    user_id: str,
    source_id: str,
    *,
    raw_input: str | None | _Unset = UNSET,
    job_link_contains: str | None | _Unset = UNSET,
    name: str | None | _Unset = UNSET,
) -> VacancySource:
    """Edit a source: its name, its link and (web) its "Job link contains".

    Arguments left as UNSET (or a null `raw_input`) keep the stored value.
    - Nothing fetched changes (same kind + handle; web: same normalized URL
      and pattern): only the name is applied.
    - Web -> web with a new URL or pattern: the listing is read (up to
      MAX_LISTING_PAGES pages, no transaction open), then one transaction
      updates the source in place (same id, so its seen history stays),
      bumps `revision`, remembers every listed job as seen and deletes the
      source's posts still waiting for the AI (they matched the old filter).
    - Another kind, or a non-web source with a new handle: the new source is
      checked live exactly like `add_source`, then one transaction removes the
      old one (`_delete_source_rows`) and inserts the new one, which gets the
      normal first scan (web: listed jobs are seen). The NEW source is
      returned.
    Web in-place edits keep a custom name unless `name` is given. A replace
    gives the new source its own default name unless `name` sets one that
    differs from the old source's current name. The edited source is left
    out of the duplicate and MAX_SOURCES checks. `job_link_contains` is
    ignored when the result is not a web source.

    Raises:
        SourceInputError: unrecognised input, or a bad name / pattern.
        SourceNotFoundError: not one of the user's sources.
        SourceBusyError: a first-scan attempt is running (fresh lease), or
            another edit of this source was saved first.
        DuplicateSourceError: another of the user's sources has this link.
        SourceLimitError: MAX_SOURCES reached (only if already over it).
        SourceCheckError: the live check of the new link failed.
    """
    # Validate everything before any lookup or network call.
    new_name = UNSET if isinstance(name, _Unset) else normalize_source_name(name)
    parsed = (
        None
        if isinstance(raw_input, _Unset) or raw_input is None
        else parse_input(raw_input)
    )
    new_pattern = (
        UNSET
        if isinstance(job_link_contains, _Unset)
        else normalize_job_link_contains(job_link_contains)
    )

    source = await _get_owned_source(db, user_id, source_id)
    if is_attempt_running(source):
        await db.rollback()
        raise SourceBusyError
    custom_name = _custom_name(source) if isinstance(new_name, _Unset) else new_name
    # On a replace the old custom name is NOT carried over: the removed
    # source's cards keep it as their "(removed)" label, so reusing it would
    # make old and new indistinguishable. The client may echo the old name back.
    replace_name = (
        new_name
        if isinstance(new_name, str) and new_name != source.display_name
        else None
    )

    if parsed is not None and parsed.kind != source.kind:
        return await _replace_source(db, source, parsed, new_pattern, replace_name)
    if source.kind != "web":
        if parsed is not None and parsed.handle != source.handle:
            return await _replace_source(db, source, parsed, new_pattern, replace_name)
        return await rename_source(db, user_id, source_id, name)

    # Web -> web: the URL and/or the pattern may change.
    assert source.url is not None
    new_url = source.url if parsed is None else parsed.url
    assert new_url is not None
    pattern = (
        source.job_link_contains if isinstance(new_pattern, _Unset) else new_pattern
    )
    # A source stored before canonical URLs may hold another spelling of the
    # same search: compare canonical forms, so such an edit is a no-op too.
    same_url = new_url in (source.url, canonical_web_url(source.url))
    if same_url and pattern == source.job_link_contains:
        return await rename_source(db, user_id, source_id, name)
    return await _edit_web_source(
        db,
        source,
        ParsedSource(kind="web", handle="", url=new_url),
        pattern,
        custom_name,
    )


async def _edit_web_source(
    db: AsyncSession,
    source: VacancySource,
    parsed: ParsedSource,
    pattern: str | None,
    custom_name: str | None,
) -> VacancySource:
    """Change a web source's URL and/or pattern in place (see `edit_source`)."""
    assert parsed.url is not None
    user_id = source.user_id
    source_id = source.id
    revision = source.revision
    await _check_can_add(db, user_id, parsed, exclude_id=source_id)
    await db.commit()  # no transaction open during the fetch

    listing = await read_web_listing(
        parsed.url,
        pattern,
        max_pages=MAX_LISTING_PAGES,
        total_timeout_s=SAVE_TIMEOUT_SECONDS,
    )

    current = await _get_owned_source(db, user_id, source_id)
    if is_attempt_running(current):
        await db.rollback()
        raise SourceBusyError
    await _check_can_add(db, user_id, parsed, exclude_id=source_id)
    now = _now_naive()
    default_name = web_default_name(parsed.url)
    result = await db.execute(
        update(VacancySource)
        .where(VacancySource.id == source_id, VacancySource.revision == revision)
        .values(
            url=parsed.url,
            url_hash=url_hash(parsed.url),
            job_link_contains=pattern,
            default_name=default_name,
            display_name=custom_name or default_name,
            revision=VacancySource.revision + 1,
            initial_scan_completed_at=now,
            last_checked_at=now,
            failing_since=None,
            last_error=None,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        # Another edit of this source was saved while we were reading.
        await db.rollback()
        raise SourceBusyError
    await _delete_pending_rows(db, source_id, user_id)
    db.add_all(await _unseen_keys(db, user_id, source_id, listing.jobs))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateSourceError from exc
    await db.refresh(current)
    return current


async def _unseen_keys(
    db: AsyncSession, user_id: str, source_id: str, jobs: list[ListingJob]
) -> list[VacancySeenKey]:
    """Seen-key rows for the listed jobs the user has not seen yet."""
    candidates = _seen_keys(user_id, source_id, jobs)
    if not candidates:
        return []
    result = await db.execute(
        select(VacancySeenKey.external_key).where(
            VacancySeenKey.user_id == user_id,
            VacancySeenKey.external_key.in_([c.external_key for c in candidates]),
        )
    )
    known = set(result.scalars().all())
    return [c for c in candidates if c.external_key not in known]


async def _replace_source(
    db: AsyncSession,
    old: VacancySource,
    parsed: ParsedSource,
    new_pattern: str | None | _Unset,
    custom_name: str | None,
) -> VacancySource:
    """Remove `old` and add the source `parsed` describes, in one transaction
    after the live check (see `edit_source`)."""
    user_id = old.user_id
    old_id = old.id
    revision = old.revision
    await _check_can_add(db, user_id, parsed, exclude_id=old_id)
    await db.commit()  # no transaction open during the live check

    seen: list[VacancySeenKey] = []
    if parsed.kind == "web":
        assert parsed.url is not None
        pattern = None if isinstance(new_pattern, _Unset) else new_pattern
        listing = await read_web_listing(
            parsed.url,
            pattern,
            max_pages=MAX_LISTING_PAGES,
            total_timeout_s=SAVE_TIMEOUT_SECONDS,
        )
        new_source = _build_web_source(user_id, parsed, pattern, custom_name)
        seen = _seen_keys(user_id, new_source.id, listing.jobs)
    else:
        default_name = await _fetch_display_name(parsed)
        new_source = VacancySource(
            user_id=user_id,
            kind=parsed.kind,
            handle=parsed.handle,
            default_name=default_name,
            display_name=custom_name or default_name,
        )

    current = await _get_owned_source(db, user_id, old_id)
    if is_attempt_running(current) or current.revision != revision:
        # A first scan started, or another edit was saved, during the check.
        await db.rollback()
        raise SourceBusyError
    await _check_can_add(db, user_id, parsed, exclude_id=old_id)
    await _delete_source_rows(db, current)
    db.add(new_source)
    db.add_all(seen)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateSourceError from exc
    await db.refresh(new_source)
    return new_source


async def _delete_pending_rows(db: AsyncSession, source_id: str, user_id: str) -> None:
    """Delete the source's posts still waiting for the AI (incl. `needs_detail`)
    with their card sources, without committing. Their seen keys stay."""
    pending_ids = select(Vacancy.id).where(
        Vacancy.source_id == source_id,
        Vacancy.user_id == user_id,
        Vacancy.state == "pending",
    )
    await db.execute(
        delete(VacancyCardSource).where(VacancyCardSource.vacancy_id.in_(pending_ids))
    )
    await db.execute(delete(Vacancy).where(Vacancy.id.in_(pending_ids)))


async def _delete_source_rows(db: AsyncSession, source: VacancySource) -> None:
    """Remove a source and detach its cards, without committing.

    Its posts still waiting for the AI (`pending`) are deleted with their card
    sources: removing a source stops its scan. Their seen keys stay, so a
    re-added source does not show them again. Cards already in the Inbox stay;
    their references are cleared explicitly (SQLite does not enforce ON DELETE
    SET NULL here). Card sources keep the source identity and get the current
    display name as their label, so "(removed)" shows the latest name.
    """
    source_id = source.id
    await _delete_pending_rows(db, source_id, source.user_id)
    await db.execute(
        update(Vacancy).where(Vacancy.source_id == source_id).values(source_id=None)
    )
    await db.execute(
        update(VacancyCardSource)
        .where(VacancyCardSource.source_id == source_id)
        .values(label=source.display_name, source_id=None)
    )
    await db.execute(delete(VacancySource).where(VacancySource.id == source_id))


async def delete_source(db: AsyncSession, user_id: str, source_id: str) -> bool:
    """Delete one of the user's sources. Returns False if it is not theirs.

    See `_delete_source_rows` for what happens to its cards.
    """
    result = await db.execute(
        select(VacancySource).where(
            VacancySource.id == source_id, VacancySource.user_id == user_id
        )
    )
    source = result.scalar_one_or_none()
    if source is None:
        await db.rollback()
        return False
    await _delete_source_rows(db, source)
    await db.commit()
    return True
