"""Watched sources (Telegram channels, later job boards) for vacancy discovery.

Invariant: no network I/O inside a database transaction. `add_source` ends
the read transaction before the live check and writes in a short one after.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vacancy_search_settings import VacancySearchSettings
from app.models.vacancy_source import VacancySource
from app.services.vacancy_source_check import fetch_telegram_channel_title
from app.services.vacancy_source_parsing import ParsedSource, parse_source_input

MAX_SOURCES = 30
UNAVAILABLE_AFTER = timedelta(hours=24)

SOURCE_LIMIT_MESSAGE = "You can watch up to 30 sources"
DUPLICATE_SOURCE_MESSAGE = "Already in your sources"


class SourceLimitError(Exception):
    """The user already watches MAX_SOURCES sources."""


class DuplicateSourceError(Exception):
    """The same kind + handle is already in the user's sources."""


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


async def _source_exists(db: AsyncSession, user_id: str, parsed: ParsedSource) -> bool:
    result = await db.execute(
        select(VacancySource.id)
        .where(
            VacancySource.user_id == user_id,
            VacancySource.kind == parsed.kind,
            VacancySource.handle == parsed.handle,
        )
        .limit(1)
    )
    return result.first() is not None


async def _count_sources(db: AsyncSession, user_id: str) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(VacancySource)
        .where(VacancySource.user_id == user_id)
    )
    return result.scalar_one()


async def _check_can_add(db: AsyncSession, user_id: str, parsed: ParsedSource) -> None:
    if await _source_exists(db, user_id, parsed):
        raise DuplicateSourceError
    if await _count_sources(db, user_id) >= MAX_SOURCES:
        raise SourceLimitError


async def _fetch_display_name(parsed: ParsedSource) -> str:
    match parsed.kind:
        case "telegram":
            return await fetch_telegram_channel_title(parsed.handle)
        case _:  # pragma: no cover - the parser only yields telegram for now
            raise NotImplementedError(parsed.kind)


async def add_source(db: AsyncSession, user_id: str, raw_input: str) -> VacancySource:
    """Parse, check limits and duplicates, verify live, then save.

    Raises:
        SourceInputError: unrecognised input.
        DuplicateSourceError: already watched (checked before and after the
            live check; the unique constraint closes the race).
        SourceLimitError: MAX_SOURCES reached.
        SourceCheckError: the live check failed (not public / unreachable).
    """
    parsed = parse_source_input(raw_input)

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


async def delete_source(db: AsyncSession, user_id: str, source_id: str) -> bool:
    """Delete one of the user's sources. Returns False if it is not theirs."""
    result = await db.execute(
        delete(VacancySource).where(
            VacancySource.id == source_id, VacancySource.user_id == user_id
        )
    )
    await db.commit()
    return result.rowcount > 0
