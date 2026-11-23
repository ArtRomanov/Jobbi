"""Inbox queries and card actions: the card list, the new-count badge, the
discovery status, the seen / dismiss / restore transitions, and "Add to
tracker"."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import case, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ApplicationStatus
from app.core.pagination import paginate
from app.core.timezones import local_day_bounds, zone_or_utc
from app.discovery.normalize import is_http_url, normalize_url
from app.models.application import Application
from app.models.cv import Cv
from app.models.user import User
from app.models.vacancy import Vacancy, VacancyCardSource
from app.models.vacancy_search_settings import VacancySearchSettings
from app.models.vacancy_source import VacancySource
from app.schemas.application import ApplicationCreate
from app.services import application_service, cv_service

__all__ = [
    "AI_UNAVAILABLE_AFTER",
    "VISIBLE_STATES",
    "AddedToTrackerData",
    "CardSourceData",
    "DiscoveryStatusData",
    "DuplicateApplicationError",
    "ExistingApplicationData",
    "VacancyAlreadyAddedError",
    "VacancyNotFoundError",
    "VacancyNotInInboxError",
    "add_to_tracker",
    "count_new",
    "discovery_status",
    "dismiss_vacancy",
    "existing_applications",
    "list_vacancies",
    "mark_seen",
    "parse_source_key",
    "removed_sources",
    "restore_vacancy",
    "source_key",
    "tailored_cv_name",
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


@dataclass(frozen=True, slots=True, kw_only=True)
class ExistingApplicationData:
    id: str
    company_name: str
    role_title: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AddedToTrackerData:
    application_id: str
    cv_id: str | None


class VacancyNotFoundError(Exception):
    """No such card for this user, or it is still `pending` (not in the Inbox)."""


class VacancyNotInInboxError(Exception):
    """The card has left the Inbox for good (`added`, or `dismissed` where the
    action needs a visible card)."""


class VacancyAlreadyAddedError(VacancyNotInInboxError):
    """The card is already in the tracker (`added`)."""


class DuplicateApplicationError(Exception):
    """The tracker already has an application with the card's job link."""

    def __init__(self, application: ExistingApplicationData) -> None:
        super().__init__(application.id)
        self.application = application


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


def _card_link(vacancy: Vacancy) -> str:
    """The job link a card is tracked by: its job link, else the post URL."""
    return vacancy.job_link or vacancy.url


async def _application_index(
    db: AsyncSession, user_id: str
) -> dict[str, ExistingApplicationData]:
    """The user's applications by normalized `job_url`.

    Normalized in Python (no stored column): a user has few applications.
    When several share a link, the most recently updated one wins.
    """
    rows = await db.execute(
        select(
            Application.id,
            Application.company_name,
            Application.role_title,
            Application.job_url,
        )
        .where(Application.user_id == user_id, Application.job_url.is_not(None))
        .order_by(Application.updated_at.desc(), Application.id)
    )
    index: dict[str, ExistingApplicationData] = {}
    for app_id, company_name, role_title, job_url in rows:
        if not job_url.strip():
            continue
        index.setdefault(
            normalize_url(job_url),
            ExistingApplicationData(
                id=app_id, company_name=company_name, role_title=role_title
            ),
        )
    return index


async def existing_applications(
    db: AsyncSession, user_id: str, cards: list[Vacancy]
) -> dict[str, ExistingApplicationData]:
    """For each card (by id), the user's application with the same job link,
    compared after normalization (trailing slash, `utm_*`, fragment, host
    case). Cards without a match are absent."""
    if not cards:
        return {}
    index = await _application_index(db, user_id)
    if not index:
        return {}
    found: dict[str, ExistingApplicationData] = {}
    for card in cards:
        match = index.get(normalize_url(_card_link(card)))
        if match is not None:
            found[card.id] = match
    return found


_CV_NAME_MAX = Cv.__table__.c.name.type.length or 255


def tailored_cv_name(cv_name: str, company_name: str, role_title: str) -> str:
    """The copy name "<CV name> — <Company> <Role>", cut to the column length.

    An empty (or blank) company or role is left out with its space; with
    both empty the name is the CV name alone, without the dash.
    """
    target = " ".join(
        part for part in (company_name.strip(), role_title.strip()) if part
    )
    name = f"{cv_name} — {target}" if target else cv_name
    return name[:_CV_NAME_MAX]


async def add_to_tracker(
    db: AsyncSession,
    user_id: str,
    vacancy_id: str,
    *,
    company_name: str,
    role_title: str,
    notes: str | None,
    base_cv_id: str | None,
    allow_duplicate: bool,
) -> AddedToTrackerData:
    """Turn an Inbox card into an application, optionally with a copy of a
    base CV linked to it. One transaction, committed once: on any error
    nothing is persisted and the card stays in the Inbox.

    1. Conditional UPDATE `new|seen -> added` (race guard: of two concurrent
       adds exactly one changes the row; SELECT-then-UPDATE would let both).
    2. Duplicate check by normalized job link, unless `allow_duplicate`.
    3. Application in status researching; `job_url` = job link or post URL
       (None unless it is an http(s) URL);
       notes = the given notes, else the card text.
    4. With `base_cv_id` (the CV the user chose): a tailored copy named
       "<CV> — <Company> <Role>", linked both ways to the application.
    5. Card linked to the application; commit.

    Raises VacancyNotFoundError (missing, pending, another user's),
    VacancyAlreadyAddedError, VacancyNotInInboxError (dismissed),
    DuplicateApplicationError, cv_service.CvNotFoundError.
    """
    try:
        result = await db.execute(
            update(Vacancy)
            .where(
                Vacancy.id == vacancy_id,
                Vacancy.user_id == user_id,
                Vacancy.state.in_(VISIBLE_STATES),
            )
            .values(state="added")
            .execution_options(synchronize_session=False)
        )
        if not result.rowcount:
            await db.rollback()
            current = await db.scalar(
                select(Vacancy.state).where(
                    Vacancy.id == vacancy_id, Vacancy.user_id == user_id
                )
            )
            if current is None or current == "pending":
                raise VacancyNotFoundError
            if current == "added":
                raise VacancyAlreadyAddedError
            raise VacancyNotInInboxError

        row = (
            await db.execute(
                select(Vacancy.url, Vacancy.job_link, Vacancy.text).where(
                    Vacancy.id == vacancy_id
                )
            )
        ).one()
        link = row.job_link or row.url
        # Defence in depth: only an http(s) link may reach Application.job_url.
        job_url = link if link and is_http_url(link) else None

        if not allow_duplicate and job_url is not None:
            index = await _application_index(db, user_id)
            existing = index.get(normalize_url(job_url))
            if existing is not None:
                raise DuplicateApplicationError(existing)

        application = await application_service.build_application(
            db,
            user_id,
            ApplicationCreate(
                company_name=company_name,
                role_title=role_title,
                job_url=job_url,
                notes=notes if notes is not None else row.text,
                status=ApplicationStatus.RESEARCHING.value,
            ),
        )

        cv_id: str | None = None
        if base_cv_id is not None:
            base = await cv_service.get_cv(db, user_id, base_cv_id)
            if base is None:
                raise cv_service.CvNotFoundError(base_cv_id)
            copy = await cv_service.build_cv_copy(
                db,
                user_id,
                base_cv_id,
                tailored_cv_name(base.name, company_name, role_title),
                tailored_for_application_id=application.id,
            )
            application.cv_id = copy.id
            cv_id = copy.id

        await db.execute(
            update(Vacancy)
            .where(Vacancy.id == vacancy_id)
            .values(application_id=application.id)
            .execution_options(synchronize_session=False)
        )
        await db.commit()
    except Exception:
        # Every failure path, expected or not, leaves nothing behind.
        await db.rollback()
        raise
    return AddedToTrackerData(application_id=application.id, cv_id=cv_id)
