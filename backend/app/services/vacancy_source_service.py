"""Watched sources (Telegram channels, Greenhouse / Lever / Teamtailor boards,
web listing pages).

Invariant: no network I/O inside a database transaction. `add_source` and
`preview_source` end the read transaction before the live check; `add_source`
writes in a short one after.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from urllib.parse import urlsplit

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.discovery.fetchers.web_listing import AtsHint, ListingJob
from app.discovery.web_scan import MAX_LISTING_PAGES, web_seen_key
from app.models.vacancy import Vacancy, VacancyCardSource
from app.models.vacancy_search_settings import VacancySearchSettings
from app.models.vacancy_seen_key import VacancySeenKey
from app.models.vacancy_source import VacancySource
from app.services.vacancy_source_check import (
    PREVIEW_TIMEOUT_SECONDS,
    SAVE_TIMEOUT_SECONDS,
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
MAX_SOURCE_NAME_LENGTH = 100
MAX_JOB_LINK_CONTAINS_LENGTH = 100
PREVIEW_TITLES = 5

SOURCE_LIMIT_MESSAGE = "You can watch up to 30 sources"
DUPLICATE_SOURCE_MESSAGE = "Already in your sources"
NAME_TOO_LONG_MESSAGE = "Name can be up to 100 characters"
BAD_JOB_LINK_CONTAINS_MESSAGE = "'Job link contains' must be 1–100 characters"

MAX_DESCRIPTION_LENGTH = 500
MAX_EXCLUDE_TERMS = 50
MAX_EXCLUDE_TERM_LENGTH = 64

DESCRIPTION_TOO_LONG_MESSAGE = "Description can be up to 500 characters"
TOO_MANY_EXCLUDE_TERMS_MESSAGE = "You can add up to 50 exclude words"
BAD_EXCLUDE_TERM_MESSAGE = "Exclude words must be 1–64 characters"


class _Unset(Enum):
    UNSET = "unset"


UNSET = _Unset.UNSET


class SourceLimitError(Exception):
    """The user already watches MAX_SOURCES sources."""


class DuplicateSourceError(Exception):
    """The same kind + handle (web: the same normalized URL) is already watched."""


class SourceNotFoundError(Exception):
    """The given source id is not one of the user's sources."""


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


def normalize_exclude_terms(raw: list[str]) -> list[str]:
    """Trim, collapse inner whitespace, lowercase, de-duplicate keeping order.

    Raises:
        SearchSettingsError: a term is empty or too long, or too many terms
            remain after de-duplication.
    """
    terms: list[str] = []
    for item in raw:
        term = " ".join(item.split()).lower()
        if not term or len(term) > MAX_EXCLUDE_TERM_LENGTH:
            raise SearchSettingsError(BAD_EXCLUDE_TERM_MESSAGE)
        if term not in terms:
            terms.append(term)
    if len(terms) > MAX_EXCLUDE_TERMS:
        raise SearchSettingsError(TOO_MANY_EXCLUDE_TERMS_MESSAGE)
    return terms


async def update_search_settings(
    db: AsyncSession,
    user_id: str,
    *,
    description: str | None | _Unset = UNSET,
    exclude: list[str] | _Unset = UNSET,
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
    new_exclude = (
        UNSET if isinstance(exclude, _Unset) else normalize_exclude_terms(exclude)
    )

    # Two attempts: a concurrent first PATCH may insert the row between our
    # SELECT and INSERT; the primary key rejects ours and we update theirs.
    for attempt in range(2):
        settings_row = await get_search_settings(db, user_id)
        if settings_row is None:
            settings_row = VacancySearchSettings(user_id=user_id, exclude_terms=[])
            db.add(settings_row)
        if not isinstance(new_description, _Unset):
            settings_row.description = new_description
        if not isinstance(new_exclude, _Unset):
            # A new list object, so the JSON column change is detected.
            settings_row.exclude_terms = list(new_exclude)
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
        SourceCheckError: unsafe link, page not readable, or no vacancies.
    """
    parsed = parse_source_input(raw_input)
    if parsed.kind != "web":
        return SourcePreview(kind=parsed.kind)
    assert parsed.url is not None
    pattern = normalize_job_link_contains(job_link_contains)

    if source_id is not None:
        await _check_owned(db, user_id, source_id)
    await _check_can_add(db, user_id, parsed, exclude_id=source_id)
    # End the read transaction before going to the network (see add_source).
    await db.commit()

    listing = await read_web_listing(
        parsed.url,
        pattern,
        max_pages=1,
        total_timeout_s=PREVIEW_TIMEOUT_SECONDS,
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
    parsed = parse_source_input(raw_input)
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
    now = _now_naive()
    source_id = str(uuid.uuid4())
    source = VacancySource(
        id=source_id,
        user_id=user_id,
        kind="web",
        handle=source_id,
        url=parsed.url,
        url_hash=url_hash(parsed.url),
        job_link_contains=pattern,
        display_name=custom_name or web_default_name(parsed.url),
        initial_scan_completed_at=now,
        last_checked_at=now,
    )
    db.add(source)
    db.add_all(_seen_keys(user_id, source_id, listing.jobs))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateSourceError from exc
    await db.refresh(source)
    return source


def _seen_keys(
    user_id: str, source_id: str, jobs: list[ListingJob]
) -> list[VacancySeenKey]:
    keys = dict.fromkeys(web_seen_key(source_id, job.url) for job in jobs)
    return [VacancySeenKey(user_id=user_id, external_key=key) for key in keys]


async def delete_source(db: AsyncSession, user_id: str, source_id: str) -> bool:
    """Delete one of the user's sources. Returns False if it is not theirs.

    Its posts still waiting for the AI (`pending`) are deleted with their card
    sources: removing a source stops its scan. Their seen keys stay, so a
    re-added source does not show them again. Cards already in the Inbox stay;
    their references are cleared explicitly (SQLite does not enforce ON DELETE
    SET NULL here). Card sources keep the source identity and label, so the
    Inbox can still filter them.
    """
    result = await db.execute(
        delete(VacancySource).where(
            VacancySource.id == source_id, VacancySource.user_id == user_id
        )
    )
    if result.rowcount == 0:
        await db.rollback()
        return False
    pending_ids = select(Vacancy.id).where(
        Vacancy.source_id == source_id,
        Vacancy.user_id == user_id,
        Vacancy.state == "pending",
    )
    await db.execute(
        delete(VacancyCardSource).where(VacancyCardSource.vacancy_id.in_(pending_ids))
    )
    await db.execute(delete(Vacancy).where(Vacancy.id.in_(pending_ids)))
    await db.execute(
        update(Vacancy).where(Vacancy.source_id == source_id).values(source_id=None)
    )
    await db.execute(
        update(VacancyCardSource)
        .where(VacancyCardSource.source_id == source_id)
        .values(source_id=None)
    )
    await db.commit()
    return True
