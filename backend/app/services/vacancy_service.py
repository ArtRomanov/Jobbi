"""Inbox queries and card actions: the card list, the new-count badge, the
discovery status, and the seen / dismiss / restore transitions."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import case, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import paginate
from app.core.timezones import local_day_bounds, zone_or_utc
from app.models.user import User
from app.models.vacancy import Vacancy, VacancyCardSource
from app.models.vacancy_search_settings import VacancySearchSettings
from app.models.vacancy_source import VacancySource

__all__ = [
    "AI_UNAVAILABLE_AFTER",
    "VISIBLE_STATES",
    "CardSourceData",
    "DiscoveryStatusData",
    "VacancyNotFoundError",
    "VacancyNotInInboxError",
    "count_new",
    "discovery_status",
    "dismiss_vacancy",
    "list_vacancies",
    "mark_seen",
    "parse_source_key",
    "removed_sources",
    "restore_vacancy",
    "source_key",
]

VISIBLE_STATES = ("new", "seen")
AI_UNAVAILABLE_AFTER = timedelta(hours=1)

# Explicit order: alphabetical would put "low" before "medium".
_FIT_ORDER = case(
    (Vacancy.fit == "high", 0),
    (Vacancy.fit == "medium", 1),
    (Vacancy.fit == "low", 2),
    else_=3,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CardSourceData:
    key: str
    label: str


@dataclass(frozen=True, slots=True, kw_only=True)
class DiscoveryStatusData:
    ai_unavailable: bool
    limit_reached: bool
    waiting_count: int


class VacancyNotFoundError(Exception):
    """No such card for this user, or it is still `pending` (not in the Inbox)."""


class VacancyNotInInboxError(Exception):
    """The card has left the Inbox for good (`added`, or `dismissed` where the
    action needs a visible card)."""


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def source_key(kind: str, handle: str) -> str:
    """Stable identity of a source across remove / re-add: "<kind>:<handle>"."""
    return f"{kind}:{handle}"


def parse_source_key(key: str) -> tuple[str, str] | None:
    kind, sep, handle = key.partition(":")
    return (kind, handle) if sep and kind and handle else None


async def _live_labels(db: AsyncSession, user_id: str) -> dict[str, str]:
    rows = await db.execute(
        select(
            VacancySource.kind, VacancySource.handle, VacancySource.display_name
        ).where(VacancySource.user_id == user_id)
    )
    return {source_key(kind, handle): name for kind, handle, name in rows}


async def list_vacancies(
    db: AsyncSession,
    user_id: str,
    *,
    source: str | None,
    state: Literal["new", "seen", "all"],
    sort: Literal["date", "fit"],
    page: int,
    per_page: int,
) -> tuple[list[Vacancy], dict[str, list[CardSourceData]], int]:
    """One page of the user's visible cards.

    `source` is a source key ("<kind>:<handle>"); it matches cards from that
    source whether it is live, removed, or removed and re-added.

    Returns the cards, their sources by card id, and the total count. A source
    that is live is labelled with its current name, a removed one with the
    name it had when the card was found.
    """
    states = VISIBLE_STATES if state == "all" else (state,)
    query = select(Vacancy).where(Vacancy.user_id == user_id, Vacancy.state.in_(states))
    if source:
        parsed = parse_source_key(source)
        if parsed is None:
            return [], {}, 0
        kind, handle = parsed
        query = query.where(
            exists().where(
                VacancyCardSource.vacancy_id == Vacancy.id,
                VacancyCardSource.source_kind == kind,
                VacancyCardSource.source_handle == handle,
            )
        )
    if sort == "fit":
        query = query.order_by(_FIT_ORDER, Vacancy.posted_at.desc(), Vacancy.id)
    else:
        query = query.order_by(Vacancy.posted_at.desc(), Vacancy.id)

    items, total = await paginate(db, query, page, per_page)
    sources: dict[str, list[CardSourceData]] = defaultdict(list)
    if items:
        live = await _live_labels(db, user_id)
        rows = await db.execute(
            select(
                VacancyCardSource.vacancy_id,
                VacancyCardSource.source_kind,
                VacancyCardSource.source_handle,
                VacancyCardSource.label,
            ).where(VacancyCardSource.vacancy_id.in_([v.id for v in items]))
        )
        for vacancy_id, kind, handle, label in rows:
            key = source_key(kind, handle)
            sources[vacancy_id].append(
                CardSourceData(key=key, label=live.get(key, label))
            )
        for card_sources in sources.values():
            card_sources.sort(key=lambda item: (item.label.lower(), item.key))
    return items, sources, total


async def count_new(db: AsyncSession, user_id: str) -> int:
    """Cards in state `new` (the nav badge; the daily summary reuses it)."""
    return await _count_state(db, user_id, "new")


async def _count_state(db: AsyncSession, user_id: str, state: str) -> int:
    result = await db.scalar(
        select(func.count())
        .select_from(Vacancy)
        .where(Vacancy.user_id == user_id, Vacancy.state == state)
    )
    return result or 0


async def removed_sources(db: AsyncSession, user_id: str) -> list[CardSourceData]:
    """Sources of visible cards that are no longer watched: identity (kind +
    handle) not among the user's live sources. A re-added source (same kind
    and handle, even with a new title) is live again and not listed. Each is
    labelled with the name from its most recently found card."""
    live = await _live_labels(db, user_id)
    rows = await db.execute(
        select(
            VacancyCardSource.source_kind,
            VacancyCardSource.source_handle,
            VacancyCardSource.label,
            Vacancy.found_at,
        )
        .join(Vacancy, Vacancy.id == VacancyCardSource.vacancy_id)
        .where(Vacancy.user_id == user_id, Vacancy.state.in_(VISIBLE_STATES))
    )
    latest: dict[str, tuple[datetime, str]] = {}
    for kind, handle, label, found_at in rows:
        key = source_key(kind, handle)
        if key in live:
            continue
        if key not in latest or found_at > latest[key][0]:
            latest[key] = (found_at, label)
    removed = [
        CardSourceData(key=key, label=label) for key, (_, label) in latest.items()
    ]
    return sorted(removed, key=lambda item: (item.label.lower(), item.key))


async def discovery_status(
    db: AsyncSession,
    user: User,
    settings_row: VacancySearchSettings | None,
    now: datetime | None = None,
) -> DiscoveryStatusData:
    now = now or _now_naive()
    waiting = await _count_state(db, user.id, "pending")
    if settings_row is None:
        return DiscoveryStatusData(
            ai_unavailable=False, limit_reached=False, waiting_count=waiting
        )
    local_date, _, _ = local_day_bounds(now, zone_or_utc(user.timezone))
    failing_since = settings_row.ai_failing_since
    return DiscoveryStatusData(
        ai_unavailable=failing_since is not None
        and now - failing_since > AI_UNAVAILABLE_AFTER,
        limit_reached=settings_row.limit_reached_on == local_date,
        waiting_count=waiting,
    )


async def _transition(
    db: AsyncSession,
    user_id: str,
    vacancy_id: str,
    *,
    from_states: tuple[str, ...],
    to_state: str,
    noop_states: tuple[str, ...],
) -> None:
    """Move one of the user's cards `from_states -> to_state` atomically.

    A conditional UPDATE (not SELECT-then-UPDATE), so two concurrent actions
    cannot both pass the state check. When nothing changed, the current state
    decides: `noop_states` succeed silently (idempotent repeat), a missing or
    `pending` card raises VacancyNotFoundError, anything else
    VacancyNotInInboxError.
    """
    result = await db.execute(
        update(Vacancy)
        .where(
            Vacancy.id == vacancy_id,
            Vacancy.user_id == user_id,
            Vacancy.state.in_(from_states),
        )
        .values(state=to_state)
    )
    if result.rowcount:
        await db.commit()
        return
    await db.rollback()
    current = await db.scalar(
        select(Vacancy.state).where(
            Vacancy.id == vacancy_id, Vacancy.user_id == user_id
        )
    )
    if current is None or current == "pending":
        raise VacancyNotFoundError
    if current not in noop_states:
        raise VacancyNotInInboxError


async def mark_seen(db: AsyncSession, user_id: str, vacancy_id: str) -> None:
    """`new -> seen` ("Open source"). Already seen: no-op.

    Raises VacancyNotFoundError, VacancyNotInInboxError (dismissed / added).
    """
    await _transition(
        db,
        user_id,
        vacancy_id,
        from_states=("new",),
        to_state="seen",
        noop_states=("seen",),
    )


async def dismiss_vacancy(db: AsyncSession, user_id: str, vacancy_id: str) -> None:
    """`new|seen -> dismissed`. Already dismissed: no-op.

    Raises VacancyNotFoundError, VacancyNotInInboxError (added).
    """
    await _transition(
        db,
        user_id,
        vacancy_id,
        from_states=VISIBLE_STATES,
        to_state="dismissed",
        noop_states=("dismissed",),
    )


async def restore_vacancy(db: AsyncSession, user_id: str, vacancy_id: str) -> None:
    """`dismissed -> seen` (Undo). Already visible (new/seen): no-op.

    Raises VacancyNotFoundError, VacancyNotInInboxError (added).
    """
    await _transition(
        db,
        user_id,
        vacancy_id,
        from_states=("dismissed",),
        to_state="seen",
        noop_states=VISIBLE_STATES,
    )
