"""Discovery runs: read sources, store new posts, evaluate them with AI.

INVARIANT (shared SQLite file with the API and the bot): no network I/O while a
database transaction is open. Every step is either
- read: a short session that loads plain data and closes, or
- network: an HTTP fetch or a Groq call with no session open, or
- write: a short `session.begin()` block that commits on exit.
Functions never hold an ORM object across a network call; they copy what they
need into the frozen dataclasses below.

Sources: Telegram channels, Greenhouse / Lever / Teamtailor boards
(`board_scan`) and web pages (`web_scan` listing, then a detail step that
reads each new job's own page before the AI sees it).

Reposts (same `job_link` as a user's `new`/`seen`/`dismissed` card) merge into
that card as an extra `vacancy_card_sources` row. Mostly at store time, before
any AI call: the card keeps the first post's date, fit and text anyway, so
rating the repost would only spend the daily cap. Posts stored before their
card existed (e.g. two channels in one run, both pending) merge after a match.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum, auto
from typing import Any, Self, TypeAlias

import groq
import httpx
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot

from app.core.config import Settings, get_settings
from app.core.timezones import local_day_bounds, zone_or_utc
from app.discovery.alerts import send_run_alerts
from app.discovery.board_scan import BOARD_KINDS, board_key_prefix, fetch_board
from app.discovery.evaluator import (
    BATCH_SIZE,
    BatchEvaluation,
    EvaluationFormatError,
    EvaluationRateLimitedError,
    EvaluationTransportError,
    PostVerdict,
    evaluate_batch,
)
from app.discovery.fetchers import safe_http
from app.discovery.fetchers.board_http import fits_columns
from app.discovery.fetchers.errors import BoardReadError
from app.discovery.fetchers.safe_http import PageFetchError, Resolver, UnsafeUrlError
from app.discovery.fetchers.telegram import SourceReadError, fetch_channel_posts
from app.discovery.fetchers.web_job import fetch_job
from app.discovery.fetchers.web_listing import ListingJob
from app.discovery.normalize import normalize_url
from app.discovery.prefilter import excluded
from app.discovery.types import RawPost
from app.discovery.web_scan import read_listing, web_seen_key
from app.models.user import User
from app.models.vacancy import Vacancy, VacancyCardSource
from app.models.vacancy_search_settings import VacancySearchSettings
from app.models.vacancy_seen_key import VacancySeenKey
from app.models.vacancy_source import VacancySource

__all__ = [
    "CARD_RETENTION",
    "EVAL_PAUSE_S",
    "LOOKBACK",
    "MAX_EVAL_ATTEMPTS",
    "MAX_PAGES",
    "PENDING_WITHOUT_DESCRIPTION_RETENTION",
    "READ_ERROR_MESSAGES",
    "WEB_DETAIL_LIMIT",
    "WEB_RUN_BUDGET_S",
    "WEB_SOURCE_DETAIL_BUDGET_S",
    "CleanupReport",
    "Clock",
    "DiscoveryConfig",
    "RunReport",
    "check_all",
    "cleanup",
    "evaluate_pending",
    "run_initial_scans",
]

logger = logging.getLogger(__name__)

LOOKBACK = timedelta(days=7)
MAX_PAGES = 10
# One AI call per pause. gpt-oss-20b spends ~4 000-5 000 tokens per batch of 5,
# so 30 s (two calls a minute) would exceed the 8 000 tokens/minute account limit.
EVAL_PAUSE_S = 45.0
MAX_EVAL_ATTEMPTS = 3
# Seen keys of posts inside the lookback window were first seen inside it too
# (a post cannot be seen before it is posted); the margin absorbs clock skew.
_KNOWN_KEYS_MARGIN = timedelta(days=1)
_KEY_CHUNK = 500
# First-scan retry backoff: (failure streak shorter than, retry after).
# Retries land at +1, +6 and +21 min after the first failure, then hourly.
_INITIAL_BACKOFF = (
    (timedelta(minutes=1), timedelta(minutes=1)),
    (timedelta(minutes=6), timedelta(minutes=5)),
    (timedelta(minutes=21), timedelta(minutes=15)),
)
_INITIAL_BACKOFF_HOURLY = timedelta(hours=1)
# Retention (daily `cleanup`).
CARD_RETENTION = timedelta(days=30)
PENDING_WITHOUT_DESCRIPTION_RETENTION = timedelta(days=7)
# States a repost can merge into (and that retention deletes after 30 days).
_VISIBLE_STATES = ("new", "seen", "dismissed")

# Keyed by `SourceReadError.reason` (Telegram), `BoardReadError.reason` and
# the web listing outcomes (`unreachable`, `no_vacancies`).
READ_ERROR_MESSAGES = {
    "private_or_deleted": "Channel is private or deleted",
    "not_found": "Job board not found",
    "unreachable": "Could not reach the source",
    "no_vacancies": (
        "No vacancies found — check the link or the 'Job link contains' field"
    ),
}
WEB_KIND = "web"
SUPPORTED_KINDS = frozenset({"telegram", WEB_KIND}) | BOARD_KINDS
_WEB_KEY_PREFIX = "web:"

# Web sources (spec 010). Per hourly check and source: a listing read of up to
# 5 pages, then at most WEB_DETAIL_LIMIT job pages, 1 s apart.
WEB_DETAIL_LIMIT = 30
WEB_DETAIL_PAUSE_S = 1.0
# Failed job-page reads (one per check) before the row is rated by its title.
WEB_DETAIL_MAX_ATTEMPTS = 3
# Detail budget per source: stop after this many failures in a row or time.
WEB_DETAIL_MAX_FAILURES_IN_ROW = 3
WEB_SOURCE_DETAIL_BUDGET_S = 5 * 60.0
# The whole web part (listings + details) of one `check_all`.
WEB_RUN_BUDGET_S = 40 * 60.0
# One listing read (up to 5 pages, each up to 15 s, 1 s apart).
WEB_LISTING_TIMEOUT_S = 90.0

SessionFactory: TypeAlias = Callable[[], AsyncSession]
# Returns the current time as naive UTC. Called per source and per AI batch,
# so long runs (30 s between batches) keep real timestamps and local days.
Clock: TypeAlias = Callable[[], datetime]
SleepFn: TypeAlias = Callable[[float], Awaitable[None]]
# Seconds from an arbitrary start (`time.monotonic`); injectable for tests.
MonotonicFn: TypeAlias = Callable[[], float]


@dataclass(frozen=True, slots=True, kw_only=True)
class DiscoveryConfig:
    model: str
    daily_limit: int
    eval_pause_s: float = EVAL_PAUSE_S

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> Self:
        settings = settings or get_settings()
        return cls(
            model=settings.GROQ_DISCOVERY_MODEL,
            daily_limit=settings.DISCOVERY_DAILY_EVAL_LIMIT,
        )


@dataclass(slots=True)
class RunReport:
    """Counters for one run, logged at the end (and asserted in tests)."""

    sources_read: int = 0
    sources_failed: int = 0
    posts_stored: int = 0
    posts_excluded: int = 0
    # Reposts added as a source to an existing card (at store or after rating).
    posts_merged: int = 0
    ai_calls: int = 0
    posts_evaluated: int = 0
    matches: int = 0
    rejected: int = 0
    users_capped: set[str] = field(default_factory=set)
    # Cards that became `new` in this run, per user (input for alerts).
    new_card_ids: dict[str, list[str]] = field(default_factory=dict)
    alerts_sent: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class _SourceRef:
    id: str
    user_id: str
    kind: str
    handle: str
    display_name: str
    # Web only: the listing URL and the optional "Job link contains" filter.
    url: str | None = None
    job_link_contains: str | None = None
    # `VacancySource.revision` when loaded: results fetched under an older
    # revision (the source was edited meanwhile) are never stored.
    revision: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class _PendingRow:
    vacancy_id: str
    eval_attempts: int
    post: RawPost


@dataclass(frozen=True, slots=True, kw_only=True)
class _DetailRow:
    vacancy_id: str
    url: str
    title: str | None
    detail_attempts: int


@dataclass(frozen=True, slots=True, kw_only=True)
class _Batch:
    description: str
    profile: dict[str, Any]
    rows: list[_PendingRow]


@dataclass(frozen=True, slots=True, kw_only=True)
class _CapReached:
    local_date: date


class _Outcome(Enum):
    DONE = auto()
    STOP_USER = auto()
    STOP_RUN = auto()


class _Pacer:
    """At most one Groq call every `pause` seconds within a run (all users:
    the Groq limits are per account)."""

    def __init__(self, pause: float, sleep: SleepFn) -> None:
        self._pause = pause
        self._sleep = sleep
        self._called = False

    async def wait(self) -> None:
        if self._called:
            await self._sleep(self._pause)
        self._called = True


# --------------------------------------------------------------------------
# Public entry points
# --------------------------------------------------------------------------


async def run_initial_scans(
    session_factory: SessionFactory,
    http_client: httpx.AsyncClient,
    groq_client: groq.AsyncGroq,
    clock: Clock,
    *,
    config: DiscoveryConfig | None = None,
    sleep: SleepFn = asyncio.sleep,
    bot: Bot | None = None,
) -> RunReport:
    """First 7-day scan of every source whose first scan has not completed and
    is due (`next_initial_attempt_at` unset or passed), then evaluate the
    pending posts of the users whose sources were scanned.

    First-scan cards are never alerted. Posts of those users that were found
    by an earlier hourly check and waited (daily cap, AI down) may be rated
    here; they are alerted at the end, like in `check_all`.
    """
    config = config or DiscoveryConfig.from_settings()
    report = RunReport()
    sources = await _load_sources(session_factory, clock(), initial=True)
    if not sources:
        return report

    async def work() -> None:
        for source in sources:
            now = clock()
            if not await _take_initial_lease(session_factory, source, now):
                continue
            try:
                await _scan_source(
                    session_factory,
                    http_client,
                    source,
                    now,
                    report,
                    initial=True,
                    sleep=sleep,
                )
            finally:
                await _release_initial_lease(session_factory, source)
        await evaluate_pending(
            session_factory,
            groq_client,
            clock,
            user_ids={source.user_id for source in sources},
            config=config,
            sleep=sleep,
            report=report,
        )

    await _run_then_alert(work(), session_factory, bot, clock, report, sleep)
    _log_report("initial scans", report)
    return report


async def check_all(
    session_factory: SessionFactory,
    http_client: httpx.AsyncClient,
    groq_client: groq.AsyncGroq,
    clock: Clock,
    *,
    config: DiscoveryConfig | None = None,
    sleep: SleepFn = asyncio.sleep,
    bot: Bot | None = None,
    web_resolver: Resolver = safe_http.system_resolver,
    monotonic: MonotonicFn = time.monotonic,
) -> RunReport:
    """Hourly check: read every source with a completed first scan, store new
    posts, then evaluate the pending posts of every user with a description.

    Sources still in their first scan are skipped. One failing source does not
    stop the run. Web sources are read last, with their own guarded client
    (`safe_http`): first every web listing, then the detail step of every web
    source, all within `WEB_RUN_BUDGET_S`. At the end each user gets one
    Telegram alert (when `bot` is given and the user linked Telegram) for the
    cards that became `new` in this run, first-scan cards excluded.
    """
    config = config or DiscoveryConfig.from_settings()
    report = RunReport()

    async def work() -> None:
        sources = await _load_sources(session_factory, clock(), initial=False)
        for source in sources:
            if source.kind == WEB_KIND:
                continue
            await _scan_source(
                session_factory,
                http_client,
                source,
                clock(),
                report,
                initial=False,
                sleep=sleep,
            )
        web_sources = [source for source in sources if source.kind == WEB_KIND]
        if web_sources:
            await _check_web_sources(
                session_factory,
                web_sources,
                clock,
                report,
                sleep=sleep,
                resolver=web_resolver,
                monotonic=monotonic,
            )
        await evaluate_pending(
            session_factory,
            groq_client,
            clock,
            config=config,
            sleep=sleep,
            report=report,
        )

    await _run_then_alert(work(), session_factory, bot, clock, report, sleep)
    _log_report("hourly check", report)
    return report


async def _run_then_alert(
    work: Awaitable[None],
    session_factory: SessionFactory,
    bot: Bot | None,
    clock: Clock,
    report: RunReport,
    sleep: SleepFn,
) -> None:
    """Run `work`, then alert about the cards it made `new` — also when it
    fails half way, so those cards are not left unannounced with
    `alert_handled_at` NULL forever.

    - Success or an ordinary exception: alert normally, then re-raise.
    - Cancellation (worker shutting down), also while the alert itself is
      being sent: no network — the cards are only marked handled (one short
      write), then the cancellation goes on. They stay in the Inbox; they are
      just not announced.
    """
    try:
        await work
    except asyncio.CancelledError:
        await _alert_safely(session_factory, None, clock, report, sleep)
        raise
    except Exception:
        await _alert_safely(session_factory, bot, clock, report, sleep)
        raise
    try:
        report.alerts_sent = await send_run_alerts(
            session_factory, bot, report.new_card_ids, clock, sleep=sleep
        )
    except asyncio.CancelledError:
        # Cards already announced are handled; this marks the rest.
        await _alert_safely(session_factory, None, clock, report, sleep)
        raise


async def _alert_safely(
    session_factory: SessionFactory,
    bot: Bot | None,
    clock: Clock,
    report: RunReport,
    sleep: SleepFn,
) -> None:
    """Alert step on the failure path: never hides the original error."""
    try:
        report.alerts_sent = await send_run_alerts(
            session_factory, bot, report.new_card_ids, clock, sleep=sleep
        )
    except Exception:
        logger.exception("Alerts after an interrupted run failed")


async def evaluate_pending(
    session_factory: SessionFactory,
    groq_client: groq.AsyncGroq,
    clock: Clock,
    *,
    user_ids: Collection[str] | None = None,
    config: DiscoveryConfig | None = None,
    sleep: SleepFn = asyncio.sleep,
    report: RunReport | None = None,
) -> RunReport:
    """Evaluate `pending` posts, oldest first, within each user's daily cap.

    Users are served in order of their oldest pending post, so the queue is
    first come, first served across users. Users without a search description
    are skipped (their posts stay pending). A rate limit stops evaluation for
    the whole run; any other transport error stops it for that user and sets
    `ai_failing_since`.
    """
    config = config or DiscoveryConfig.from_settings()
    report = report if report is not None else RunReport()
    pacer = _Pacer(config.eval_pause_s, sleep)
    for user_id in await _users_with_pending(session_factory, user_ids):
        outcome = await _UserEvaluation(
            session_factory=session_factory,
            groq_client=groq_client,
            user_id=user_id,
            clock=clock,
            config=config,
            pacer=pacer,
            report=report,
        ).run()
        if outcome is _Outcome.STOP_RUN:
            break
    return report


# --------------------------------------------------------------------------
# Reading sources
# --------------------------------------------------------------------------


async def _load_sources(
    session_factory: SessionFactory, now: datetime, *, initial: bool
) -> list[_SourceRef]:
    stmt = select(VacancySource).where(VacancySource.kind.in_(sorted(SUPPORTED_KINDS)))
    if initial:
        # Web sources record what is listed at save time; never a first scan.
        stmt = stmt.where(
            VacancySource.kind != WEB_KIND,
            VacancySource.initial_scan_completed_at.is_(None),
            (VacancySource.next_initial_attempt_at.is_(None))
            | (VacancySource.next_initial_attempt_at <= now),
        )
    else:
        stmt = stmt.where(VacancySource.initial_scan_completed_at.is_not(None))
    # Least recently checked first (never checked before all others), so a
    # source left out by the time budget goes first in the next check.
    # `IS NOT NULL` sorts False first on every backend (portable NULLS FIRST).
    stmt = stmt.order_by(
        VacancySource.last_checked_at.is_not(None),
        VacancySource.last_checked_at,
        VacancySource.created_at,
        VacancySource.id,
    )
    async with session_factory() as session:
        sources = (await session.scalars(stmt)).all()
        return [
            _SourceRef(
                id=s.id,
                user_id=s.user_id,
                kind=s.kind,
                handle=s.handle,
                display_name=s.display_name,
                url=s.url,
                job_link_contains=s.job_link_contains,
                revision=s.revision,
            )
            for s in sources
        ]


def _same_source(source: _SourceRef) -> Any:
    """WHERE clause: the source still exists and was not edited since loaded."""
    return and_(
        VacancySource.id == source.id, VacancySource.revision == source.revision
    )


async def _revision_unchanged(session: AsyncSession, source: _SourceRef) -> bool:
    """The source still exists and was not edited since it was loaded."""
    current = await session.scalar(
        select(VacancySource.revision).where(VacancySource.id == source.id)
    )
    return current == source.revision


async def _take_initial_lease(
    session_factory: SessionFactory, source: _SourceRef, now: datetime
) -> bool:
    """Mark a first-scan attempt as running (edits get 409 meanwhile).

    False when the source was deleted or edited since it was loaded: skip it.
    """
    async with session_factory() as session, session.begin():
        result = await session.execute(
            update(VacancySource)
            .where(_same_source(source))
            .values(initial_attempt_started_at=now)
        )
    if result.rowcount == 0:
        logger.info("Source %s changed before its first scan attempt", source.id)
        return False
    return True


async def _release_initial_lease(
    session_factory: SessionFactory, source: _SourceRef
) -> None:
    """End the first-scan attempt (success or failure). A deleted source
    updates nothing; a failure here is only logged: the lease turns stale
    after 10 min anyway, and the scan's own error must not be hidden."""
    try:
        async with session_factory() as session, session.begin():
            await session.execute(
                update(VacancySource)
                .where(VacancySource.id == source.id)
                .values(initial_attempt_started_at=None)
            )
    except Exception:
        logger.exception("Could not release the first-scan lease of %s", source.id)


async def _recent_keys(
    session_factory: SessionFactory, source: _SourceRef, cutoff: datetime
) -> set[str]:
    """The user's seen keys of this channel that can still appear in a fetch."""
    stmt = select(VacancySeenKey.external_key).where(
        VacancySeenKey.user_id == source.user_id,
        VacancySeenKey.external_key.startswith(f"tg:{source.handle}/", autoescape=True),
        VacancySeenKey.first_seen_at >= cutoff - _KNOWN_KEYS_MARGIN,
    )
    async with session_factory() as session:
        return set((await session.scalars(stmt)).all())


async def _board_keys(session_factory: SessionFactory, source: _SourceRef) -> set[str]:
    """Every seen key of this board for the user. Board jobs stay listed for
    weeks, so there is no time cutoff (a board lists at most ~1 000 jobs)."""
    prefix = board_key_prefix(source.kind, source.handle)
    stmt = select(VacancySeenKey.external_key).where(
        VacancySeenKey.user_id == source.user_id,
        VacancySeenKey.external_key.startswith(prefix, autoescape=True),
    )
    async with session_factory() as session:
        return set((await session.scalars(stmt)).all())


async def _fetch_source(
    session_factory: SessionFactory,
    http_client: httpx.AsyncClient,
    source: _SourceRef,
    now: datetime,
    *,
    initial: bool,
    sleep: SleepFn,
) -> tuple[list[RawPost], list[str]]:
    """Read one source: (posts to store as pending, keys to record as seen only).

    Raises:
        SourceReadError / BoardReadError: the source could not be read.
        ValueError: the stored handle or kind no longer passes validation.
    """
    cutoff = now - LOOKBACK
    if source.kind in BOARD_KINDS:
        board = await fetch_board(
            http_client,
            source.kind,
            source.handle,
            await _board_keys(session_factory, source),
            now=now,
            cutoff=cutoff,
            initial=initial,
            sleep=sleep,
        )
        return board.posts, board.seen_only_keys
    # The first scan stores every post of the window that is not yet a seen
    # key (filtered at insert), so a re-added source skips what it showed before.
    known = set() if initial else await _recent_keys(session_factory, source, cutoff)
    posts = await fetch_channel_posts(
        http_client, source.handle, known, cutoff, MAX_PAGES, sleep=sleep
    )
    return posts, []


async def _scan_source(
    session_factory: SessionFactory,
    http_client: httpx.AsyncClient,
    source: _SourceRef,
    now: datetime,
    report: RunReport,
    *,
    initial: bool,
    sleep: SleepFn,
) -> None:
    try:
        posts, seen_only_keys = await _fetch_source(
            session_factory, http_client, source, now, initial=initial, sleep=sleep
        )
    except (SourceReadError, BoardReadError) as exc:
        logger.warning("Source %s could not be read: %s", source.id, exc)
        await _record_read_failure(
            session_factory, source, READ_ERROR_MESSAGES[exc.reason], now, initial
        )
        report.sources_failed += 1
        return
    except ValueError:  # handle no longer passes validation (or bad data)
        logger.warning("Source %s has an invalid handle", source.id)
        await _record_read_failure(
            session_factory, source, READ_ERROR_MESSAGES["unreachable"], now, initial
        )
        report.sources_failed += 1
        return
    except Exception:
        # Anything else (a parser bug on hostile content) is this source's
        # problem only: the run goes on with the other sources.
        logger.exception("Source %s failed unexpectedly", source.id)
        await _record_failure_safely(session_factory, source, now, initial=initial)
        report.sources_failed += 1
        return
    try:
        await _store_posts(
            session_factory,
            source,
            posts,
            now,
            report,
            initial=initial,
            seen_only_keys=seen_only_keys,
        )
    except Exception:
        logger.exception("Source %s: storing its posts failed", source.id)
        report.sources_failed += 1


async def _record_failure_safely(
    session_factory: SessionFactory,
    source: _SourceRef,
    now: datetime,
    *,
    initial: bool,
) -> None:
    """Record an `unreachable` read after an unexpected error; a failure of
    the write itself is only logged, so it never stops the run."""
    try:
        await _record_read_failure(
            session_factory, source, READ_ERROR_MESSAGES["unreachable"], now, initial
        )
    except Exception:
        logger.exception("Could not record the failed read of %s", source.id)


def _next_initial_attempt(now: datetime, failing_since: datetime | None) -> datetime:
    """When a failed first scan is retried: 1, 5, 15 min after the 1st, 2nd and
    3rd failure, then hourly.

    The failure count is derived from `failing_since` (the first failure of
    this streak, kept until a success), so no counter column is needed. With
    retries at +1, +6 and +21 min, a failure less than 1 min after the first
    one is the 1st, less than 6 min the 2nd, less than 21 min the 3rd.
    """
    elapsed = now - (failing_since or now)
    for streak_end, delay in _INITIAL_BACKOFF:
        if elapsed < streak_end:
            return now + delay
    return now + _INITIAL_BACKOFF_HOURLY


async def _record_read_failure(
    session_factory: SessionFactory,
    source: _SourceRef,
    message: str,
    now: datetime,
    initial: bool,
) -> None:
    """Record a failed read. Skipped when the source was deleted or edited
    during the read: the failure was about the old link."""
    async with session_factory() as session, session.begin():
        values: dict[str, Any] = {
            "failing_since": func.coalesce(VacancySource.failing_since, now),
            "last_error": message,
        }
        if initial:
            failing_since = await session.scalar(
                select(VacancySource.failing_since).where(VacancySource.id == source.id)
            )
            values["next_initial_attempt_at"] = _next_initial_attempt(
                now, failing_since
            )
        result = await session.execute(
            update(VacancySource).where(_same_source(source)).values(**values)
        )
        if result.rowcount == 0:
            logger.info("Source %s was removed or edited during its read", source.id)


async def _store_posts(
    session_factory: SessionFactory,
    source: _SourceRef,
    posts: Sequence[RawPost],
    now: datetime,
    report: RunReport,
    *,
    initial: bool,
    seen_only_keys: Sequence[str] = (),
    needs_detail: bool = False,
) -> None:
    """Record seen keys and insert `pending` cards in one short transaction.

    `seen_only_keys` (board initial scan: jobs outside the window) are only
    recorded as seen, so they never become cards later. `needs_detail` (web
    listing items) keeps the new cards away from the AI until the detail
    step has read their job page.
    """
    values: dict[str, Any] = {
        "last_checked_at": now,
        "failing_since": None,
        "last_error": None,
    }
    if initial:
        values |= {"initial_scan_completed_at": now, "next_initial_attempt_at": None}

    async with session_factory() as session, session.begin():
        # Update the source first: if it was deleted or edited (`revision`
        # bumped) during the fetch, nothing is stored: the results belong to
        # the old link/filter. The UPDATE also takes the write lock, so a
        # concurrent delete or edit waits for this transaction.
        result = await session.execute(
            update(VacancySource).where(_same_source(source)).values(**values)
        )
        if result.rowcount == 0:
            logger.info("Source %s was removed or edited during its scan", source.id)
            return
        report.sources_read += 1
        if not posts and not seen_only_keys:
            return

        exclude_terms: list[str] = (
            await session.scalar(
                select(VacancySearchSettings.exclude_terms).where(
                    VacancySearchSettings.user_id == source.user_id
                )
            )
            or []
        )
        keys = [post.external_key for post in posts] + list(seen_only_keys)
        seen = await _already_seen(session, source.user_id, keys)
        for key in seen_only_keys:
            if key in seen:
                continue
            seen.add(key)
            session.add(
                VacancySeenKey(
                    user_id=source.user_id, external_key=key, first_seen_at=now
                )
            )

        for post in posts:
            if post.external_key in seen:
                continue
            seen.add(post.external_key)
            session.add(
                VacancySeenKey(
                    user_id=source.user_id,
                    external_key=post.external_key,
                    first_seen_at=now,
                )
            )
            if excluded(post.title, post.text, exclude_terms):
                report.posts_excluded += 1
                continue
            # A repost of a job already on a card: add this source to that card
            # (no AI call; the card keeps the first post's date, fit and text).
            if post.job_link is not None and (
                target_id := await _merge_target(session, source.user_id, post.job_link)
            ):
                await _add_card_source(session, target_id, source)
                report.posts_merged += 1
                continue
            vacancy_id = str(uuid.uuid4())
            session.add(
                Vacancy(
                    id=vacancy_id,
                    user_id=source.user_id,
                    source_id=source.id,
                    external_key=post.external_key,
                    url=post.url,
                    job_link=post.job_link,
                    title=post.title,
                    company=post.company,
                    text=post.text,
                    posted_at=post.posted_at,
                    found_at=now,
                    state="pending",
                    needs_detail=needs_detail,
                    from_initial_scan=initial,
                    # First-scan cards are never alerted.
                    alert_handled_at=now if initial else None,
                )
            )
            session.add(
                VacancyCardSource(
                    vacancy_id=vacancy_id,
                    source_id=source.id,
                    source_kind=source.kind,
                    source_handle=source.handle,
                    label=source.display_name,
                )
            )
            report.posts_stored += 1


async def _merge_target(
    session: AsyncSession,
    user_id: str,
    job_link: str,
    *,
    exclude_id: str | None = None,
) -> str | None:
    """The user's oldest `new`/`seen`/`dismissed` card with this job link.

    `pending` (not rated yet) and `added` (lives on as an application) cards
    are never merge targets. Telegram posts without an external link have no
    `job_link`, so they never merge.
    """
    stmt = (
        select(Vacancy.id)
        .where(
            Vacancy.user_id == user_id,
            Vacancy.job_link == job_link,
            Vacancy.state.in_(_VISIBLE_STATES),
        )
        .order_by(Vacancy.found_at, Vacancy.id)
        .limit(1)
    )
    if exclude_id is not None:
        stmt = stmt.where(Vacancy.id != exclude_id)
    return await session.scalar(stmt)


async def _has_card_source(
    session: AsyncSession, vacancy_id: str, kind: str, handle: str
) -> bool:
    found = await session.scalar(
        select(VacancyCardSource.id)
        .where(
            VacancyCardSource.vacancy_id == vacancy_id,
            VacancyCardSource.source_kind == kind,
            VacancyCardSource.source_handle == handle,
        )
        .limit(1)
    )
    return found is not None


async def _add_card_source(
    session: AsyncSession, vacancy_id: str, source: _SourceRef
) -> None:
    """List `source` on the card, once per source identity (kind + handle)."""
    if await _has_card_source(session, vacancy_id, source.kind, source.handle):
        return
    session.add(
        VacancyCardSource(
            vacancy_id=vacancy_id,
            source_id=source.id,
            source_kind=source.kind,
            source_handle=source.handle,
            label=source.display_name,
        )
    )


async def _merge_pending_into(
    session: AsyncSession, pending_id: str, target_id: str
) -> None:
    """Move a rated repost's sources onto `target_id`, then delete the repost
    (its seen key stays, so it never comes back)."""
    card_sources = (
        await session.scalars(
            select(VacancyCardSource).where(VacancyCardSource.vacancy_id == pending_id)
        )
    ).all()
    for card_source in card_sources:
        if await _has_card_source(
            session, target_id, card_source.source_kind, card_source.source_handle
        ):
            continue
        card_source.vacancy_id = target_id
    await session.flush()
    await _delete_pending(session, pending_id)


# A user's own decision outranks a fresh `new` (see `_promote_earlier_pending`).
_STATE_RANK = {"new": 0, "seen": 1, "dismissed": 2}


async def _promote_earlier_pending(
    session: AsyncSession, pending_id: str, target_id: str, verdict: PostVerdict
) -> bool:
    """If the rated pending post was found before the card it would merge into,
    make it the card instead (spec 2.2: the card keeps the first post's date,
    fit and text) and merge the later card into it. Returns False (nothing
    changed) when the existing card came first.

    The promoted card takes the later card's user state (`seen`/`dismissed`
    outrank `new`) and its `alert_handled_at`, so a decision is not undone
    and an alert is not repeated. The later card's seen key stays.
    """
    pending = await session.get(Vacancy, pending_id)
    target = (
        await session.scalars(
            select(Vacancy).where(Vacancy.id == target_id).with_for_update()
        )
    ).one_or_none()
    if pending is None or target is None or pending.state != "pending":
        return False
    if (pending.found_at, pending.posted_at) >= (target.found_at, target.posted_at):
        return False

    state = max("new", target.state, key=lambda value: _STATE_RANK.get(value, 0))
    card_sources = (
        await session.scalars(
            select(VacancyCardSource).where(VacancyCardSource.vacancy_id == target_id)
        )
    ).all()
    for card_source in card_sources:
        if await _has_card_source(
            session, pending_id, card_source.source_kind, card_source.source_handle
        ):
            continue
        card_source.vacancy_id = pending_id
    await session.flush()
    await session.execute(
        delete(VacancyCardSource).where(VacancyCardSource.vacancy_id == target_id)
    )
    await session.execute(delete(Vacancy).where(Vacancy.id == target_id))
    await session.execute(
        update(Vacancy)
        .where(Vacancy.id == pending_id, Vacancy.state == "pending")
        .values(
            state=state,
            fit=verdict.fit.value if verdict.fit is not None else None,
            fit_reason=verdict.reason or None,
            **_named_values(pending.external_key, verdict),
            alert_handled_at=func.coalesce(
                Vacancy.alert_handled_at, target.alert_handled_at
            ),
        )
    )
    return True


async def _already_seen(
    session: AsyncSession, user_id: str, keys: Sequence[str]
) -> set[str]:
    """Which of `keys` the user has seen. Chunked: a board's first scan can
    record ~1 000 keys, above old SQLite's 999 bound-parameter limit."""
    seen: set[str] = set()
    for start in range(0, len(keys), _KEY_CHUNK):
        chunk = list(keys[start : start + _KEY_CHUNK])
        seen.update(
            (
                await session.scalars(
                    select(VacancySeenKey.external_key).where(
                        VacancySeenKey.user_id == user_id,
                        VacancySeenKey.external_key.in_(chunk),
                    )
                )
            ).all()
        )
    return seen


# --------------------------------------------------------------------------
# Web page sources: listing, then detail step
# --------------------------------------------------------------------------


async def _check_web_sources(
    session_factory: SessionFactory,
    sources: Sequence[_SourceRef],
    clock: Clock,
    report: RunReport,
    *,
    sleep: SleepFn,
    resolver: Resolver,
    monotonic: MonotonicFn,
) -> None:
    """The web part of an hourly check, within `WEB_RUN_BUDGET_S`.

    Listings of all sources first (new vacancies get queued everywhere), then
    the detail step of every source — also of one whose listing just failed,
    so rows queued before still progress. Work left when the budget is spent
    waits for the next check.
    """
    run_deadline = monotonic() + WEB_RUN_BUDGET_S
    durations = dict.fromkeys((source.id for source in sources), 0.0)
    async with safe_http.make_client() as client:
        for source in sources:
            remaining = run_deadline - monotonic()
            if remaining <= 0:
                logger.warning("Web budget spent: listings of later sources wait")
                break
            started = monotonic()
            now = clock()
            try:
                await _list_web_source(
                    session_factory,
                    client,
                    source,
                    now,
                    report,
                    sleep=sleep,
                    resolver=resolver,
                    timeout_s=min(WEB_LISTING_TIMEOUT_S, remaining),
                )
            except Exception:
                # E.g. a failed write after the read: this source only.
                logger.exception("Web source %s listing failed unexpectedly", source.id)
                report.sources_failed += 1
            durations[source.id] += monotonic() - started
        for source in await _by_longest_waiting_row(session_factory, sources):
            if monotonic() >= run_deadline:
                logger.warning("Web budget spent: job pages of later sources wait")
                break
            started = monotonic()
            try:
                await _read_job_pages(
                    session_factory,
                    client,
                    source,
                    clock,
                    report,
                    sleep=sleep,
                    resolver=resolver,
                    monotonic=monotonic,
                    deadline=min(started + WEB_SOURCE_DETAIL_BUDGET_S, run_deadline),
                )
            except Exception:
                logger.exception(
                    "Web source %s job pages failed unexpectedly", source.id
                )
            durations[source.id] += monotonic() - started
    for source in sources:
        logger.info("Web source %s checked in %.1f s", source.id, durations[source.id])


async def _by_longest_waiting_row(
    session_factory: SessionFactory, sources: Sequence[_SourceRef]
) -> list[_SourceRef]:
    """Sources for the detail step: the one whose oldest `needs_detail` row
    waits longest first, sources with nothing waiting last.

    Listing order alone would starve late sources: every listing that reads
    fine sets `last_checked_at`, so the same sources would come first every
    hour and the ones after the 40-minute budget would never get job pages.
    """
    ids = [source.id for source in sources]
    oldest: dict[str, datetime] = {}
    async with session_factory() as session:
        for start in range(0, len(ids), _KEY_CHUNK):
            rows = await session.execute(
                select(Vacancy.source_id, func.min(Vacancy.found_at))
                .where(
                    Vacancy.source_id.in_(ids[start : start + _KEY_CHUNK]),
                    Vacancy.state == "pending",
                    Vacancy.needs_detail.is_(True),
                )
                .group_by(Vacancy.source_id)
            )
            oldest.update({source_id: found for source_id, found in rows.all()})
    position = {source_id: index for index, source_id in enumerate(ids)}
    return sorted(
        sources,
        key=lambda source: (
            source.id not in oldest,
            oldest.get(source.id) or datetime.min,
            position[source.id],
        ),
    )


def _listing_post(source: _SourceRef, job: ListingJob, now: datetime) -> RawPost | None:
    """A listing item as a pending post: link and listing title, no text yet."""
    key = web_seen_key(source.id, job.url)
    link = normalize_url(job.url)
    if not fits_columns(key, link):
        return None
    return RawPost(
        external_key=key,
        url=link,
        job_link=link,
        title=job.title or None,
        company=None,
        text="",
        posted_at=now,
    )


async def _list_web_source(
    session_factory: SessionFactory,
    client: httpx.AsyncClient,
    source: _SourceRef,
    now: datetime,
    report: RunReport,
    *,
    sleep: SleepFn,
    resolver: Resolver,
    timeout_s: float,
) -> None:
    """Read the listing (up to 5 pages, stopping after a page that holds a
    seen job) and store the new jobs as `pending` + `needs_detail`.

    After each page only that page's keys are looked up (a short read session
    between two fetches, never during one), so the work does not grow with
    the source's history. Seen jobs on a page read without the check (the
    last one) are filtered out when stored.
    """
    known: set[str] = set()

    async def holds_seen_job(page_jobs: list[ListingJob]) -> bool:
        keys = [web_seen_key(source.id, job.url) for job in page_jobs]
        async with session_factory() as session:
            seen = await _already_seen(session, source.user_id, keys)
        known.update(seen)
        return bool(seen)

    reason: str | None = None
    jobs: list[ListingJob] = []
    if not source.url:
        reason = "unreachable"
    else:
        try:
            listing = await read_listing(
                source.url,
                source.job_link_contains,
                total_timeout_s=timeout_s,
                client=client,
                resolver=resolver,
                sleep=sleep,
                stop_after=holds_seen_job,
            )
        except UnsafeUrlError:
            # E.g. the host now resolves to a private address.
            reason = "unreachable"
        except PageFetchError as exc:
            logger.info("Web source %s listing failed: %s", source.id, exc.reason)
            reason = "unreachable"
        except Exception:
            # E.g. a parser bug on a hostile page: a failed read of this source.
            logger.exception("Web source %s listing failed unexpectedly", source.id)
            reason = "unreachable"
        else:
            jobs = listing.jobs
            if not jobs:
                reason = "no_vacancies"
    if reason is not None:
        logger.warning("Web source %s could not be read: %s", source.id, reason)
        await _record_read_failure(
            session_factory, source, READ_ERROR_MESSAGES[reason], now, initial=False
        )
        report.sources_failed += 1
        return

    posts = [
        post
        for job in jobs
        if (post := _listing_post(source, job, now)) is not None
        and post.external_key not in known
    ]
    await _store_posts(
        session_factory, source, posts, now, report, initial=False, needs_detail=True
    )


async def _detail_rows(
    session_factory: SessionFactory, source: _SourceRef
) -> list[_DetailRow]:
    """Up to `WEB_DETAIL_LIMIT` rows of this source waiting for their job page,
    oldest first; none when the user has no search description (the rows
    wait, and retention drops them after 7 days)."""
    async with session_factory() as session:
        description = await session.scalar(
            select(VacancySearchSettings.description).where(
                VacancySearchSettings.user_id == source.user_id
            )
        )
        if not (description or "").strip():
            return []
        rows = (
            await session.execute(
                select(Vacancy.id, Vacancy.url, Vacancy.title, Vacancy.detail_attempts)
                .where(
                    Vacancy.source_id == source.id,
                    Vacancy.state == "pending",
                    Vacancy.needs_detail.is_(True),
                )
                .order_by(Vacancy.found_at, Vacancy.id)
                .limit(WEB_DETAIL_LIMIT)
            )
        ).all()
    return [
        _DetailRow(vacancy_id=id_, url=url, title=title, detail_attempts=attempts)
        for id_, url, title, attempts in rows
    ]


async def _read_job_pages(
    session_factory: SessionFactory,
    client: httpx.AsyncClient,
    source: _SourceRef,
    clock: Clock,
    report: RunReport,
    *,
    sleep: SleepFn,
    resolver: Resolver,
    monotonic: MonotonicFn,
    deadline: float,
) -> None:
    """Detail step of one web source: read job pages one by one, 1 s apart,
    until the rows, `deadline` or `WEB_DETAIL_MAX_FAILURES_IN_ROW` run out.

    Each page is fetched with no session open, then written in its own short
    transaction. Each write first re-reads the source's `revision`: when the
    source was edited or deleted meanwhile, the step stops for this source.
    """
    failures_in_row = 0
    for index, row in enumerate(await _detail_rows(session_factory, source)):
        if index:
            await sleep(WEB_DETAIL_PAUSE_S)
        if monotonic() >= deadline:
            logger.info("Web source %s: job pages wait (time budget)", source.id)
            return
        try:
            page = await fetch_job(row.url, client=client, resolver=resolver)
        except PageFetchError as exc:
            if exc.reason == "not_found":
                # The job is gone: drop the row, keep the seen key, no AI.
                failures_in_row = 0
                if not await _drop_detail_row(session_factory, source, row):
                    return _stop_edited(source)
                continue
            if not await _count_detail_failure(session_factory, source, row):
                return _stop_edited(source)
            failures_in_row += 1
        except UnsafeUrlError:
            if not await _count_detail_failure(session_factory, source, row):
                return _stop_edited(source)
            failures_in_row += 1
        except Exception:
            # E.g. a parser bug on a hostile page. Counted like a failed read
            # (released after 3); this source's step stops for this check.
            logger.exception("Web source %s: job page failed unexpectedly", source.id)
            if not await _count_detail_failure(session_factory, source, row):
                return _stop_edited(source)
            return None
        else:
            failures_in_row = 0
            if not await _fill_detail(
                session_factory,
                source,
                row,
                text=page.text,
                posted_at=page.posted_at,
                title=page.title,
                company=page.company,
                report=report,
            ):
                return _stop_edited(source)
            continue
        if failures_in_row >= WEB_DETAIL_MAX_FAILURES_IN_ROW:
            logger.info("Web source %s: job pages wait (failures)", source.id)
            return


def _stop_edited(source: _SourceRef) -> None:
    logger.info("Web source %s was edited or removed: job pages stop", source.id)


async def _drop_detail_row(
    session_factory: SessionFactory, source: _SourceRef, row: _DetailRow
) -> bool:
    """False (nothing written) when the source changed since it was loaded."""
    async with session_factory() as session, session.begin():
        if not await _revision_unchanged(session, source):
            return False
        await _delete_pending(session, row.vacancy_id)
    return True


async def _count_detail_failure(
    session_factory: SessionFactory, source: _SourceRef, row: _DetailRow
) -> bool:
    """One more failed read; at the last one the row is rated by its title.
    False (nothing written) when the source changed since it was loaded."""
    attempts = row.detail_attempts + 1
    values: dict[str, Any] = {"detail_attempts": attempts}
    if attempts >= WEB_DETAIL_MAX_ATTEMPTS:
        # Never empty: a row without a listing title is rated by its link.
        values |= {"needs_detail": False, "text": row.title or row.url}
    async with session_factory() as session, session.begin():
        if not await _revision_unchanged(session, source):
            return False
        await session.execute(
            update(Vacancy)
            .where(
                Vacancy.id == row.vacancy_id,
                Vacancy.state == "pending",
                Vacancy.needs_detail.is_(True),
            )
            .values(**values)
        )
    return True


async def _fill_detail(
    session_factory: SessionFactory,
    source: _SourceRef,
    row: _DetailRow,
    *,
    text: str,
    posted_at: datetime | None,
    title: str | None,
    company: str | None,
    report: RunReport,
) -> bool:
    """Store the job page; an exclude word in it drops the row (seen key kept).
    False (nothing written) when the source changed since it was loaded."""
    title = title or row.title
    text = text or title or ""
    async with session_factory() as session, session.begin():
        if not await _revision_unchanged(session, source):
            return False
        exclude_terms: list[str] = (
            await session.scalar(
                select(VacancySearchSettings.exclude_terms).where(
                    VacancySearchSettings.user_id == source.user_id
                )
            )
            or []
        )
        if excluded(title, text, exclude_terms):
            await _delete_pending(session, row.vacancy_id)
            report.posts_excluded += 1
            return True
        values: dict[str, Any] = {
            "needs_detail": False,
            "text": text,
            "title": title,
        }
        if company:
            values["company"] = company
        if posted_at is not None:
            values["posted_at"] = posted_at
        await session.execute(
            update(Vacancy)
            .where(
                Vacancy.id == row.vacancy_id,
                Vacancy.state == "pending",
                Vacancy.needs_detail.is_(True),
            )
            .values(**values)
        )
    return True


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------


async def _users_with_pending(
    session_factory: SessionFactory, user_ids: Collection[str] | None
) -> list[str]:
    """Users with a description and at least one pending post, the one whose
    oldest pending post waits longest first. (The API stores a blank
    description as NULL; `_next_batch` re-checks after stripping.)"""
    stmt = (
        select(Vacancy.user_id)
        .join(VacancySearchSettings, VacancySearchSettings.user_id == Vacancy.user_id)
        .where(
            Vacancy.state == "pending",
            Vacancy.needs_detail.is_(False),
            VacancySearchSettings.description.is_not(None),
        )
        .group_by(Vacancy.user_id)
        .order_by(func.min(Vacancy.found_at), Vacancy.user_id)
    )
    if user_ids is not None:
        if not user_ids:
            return []
        stmt = stmt.where(Vacancy.user_id.in_(list(user_ids)))
    async with session_factory() as session:
        return list((await session.scalars(stmt)).all())


def _profile(user: User) -> dict[str, Any]:
    return {
        "desired_role": user.desired_role,
        "desired_location": user.desired_location,
        "remote_preference": user.remote_preference,
        "salary_min": user.salary_min,
        "salary_max": user.salary_max,
        "salary_currency": user.salary_currency,
    }


async def _next_batch(
    session_factory: SessionFactory,
    user_id: str,
    now: datetime,
    daily_limit: int,
    skip_ids: Collection[str],
) -> _Batch | _CapReached | None:
    """The next batch to evaluate, `_CapReached`, or None when there is nothing
    to do (no description, nothing pending)."""
    async with session_factory() as session:
        settings_row = await session.get(VacancySearchSettings, user_id)
        user = await session.get(User, user_id)
        if settings_row is None or user is None:
            return None
        description = (settings_row.description or "").strip()
        if not description:
            return None

        local_date, day_start, day_end = local_day_bounds(
            now, zone_or_utc(user.timezone)
        )
        used = await session.scalar(
            select(func.count())
            .select_from(VacancySeenKey)
            .where(
                VacancySeenKey.user_id == user_id,
                VacancySeenKey.evaluated_at >= day_start,
                VacancySeenKey.evaluated_at < day_end,
            )
        )
        remaining = daily_limit - (used or 0)

        stmt = (
            select(Vacancy)
            .where(
                Vacancy.user_id == user_id,
                Vacancy.state == "pending",
                Vacancy.needs_detail.is_(False),
            )
            .order_by(
                Vacancy.found_at, Vacancy.posted_at, Vacancy.external_key, Vacancy.id
            )
            .limit(max(1, min(BATCH_SIZE, remaining)))
        )
        if skip_ids:
            stmt = stmt.where(Vacancy.id.not_in(list(skip_ids)))
        rows = (await session.scalars(stmt)).all()
        if not rows:
            return None
        if remaining <= 0:
            return _CapReached(local_date=local_date)
        return _Batch(
            description=description,
            profile=_profile(user),
            rows=[
                _PendingRow(
                    vacancy_id=row.id,
                    eval_attempts=row.eval_attempts,
                    post=RawPost(
                        external_key=row.external_key,
                        url=row.url,
                        job_link=row.job_link,
                        title=row.title,
                        company=row.company,
                        text=row.text,
                        posted_at=row.posted_at,
                    ),
                )
                for row in rows
            ],
        )


class _UserEvaluation:
    """Evaluates one user's pending posts for one run."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        groq_client: groq.AsyncGroq,
        user_id: str,
        clock: Clock,
        config: DiscoveryConfig,
        pacer: _Pacer,
        report: RunReport,
    ) -> None:
        self._session_factory = session_factory
        self._groq = groq_client
        self._user_id = user_id
        self._clock = clock
        self._config = config
        self._pacer = pacer
        self._report = report
        # Posts without a valid verdict wait for the next run (one attempt per
        # run), so a stubborn post cannot make this loop call the AI forever.
        self._skip_ids: set[str] = set()

    async def run(self) -> _Outcome:
        while True:
            batch = await _next_batch(
                self._session_factory,
                self._user_id,
                self._clock(),
                self._config.daily_limit,
                self._skip_ids,
            )
            if batch is None:
                return _Outcome.DONE
            if isinstance(batch, _CapReached):
                await _set_limit_reached(
                    self._session_factory, self._user_id, batch.local_date
                )
                self._report.users_capped.add(self._user_id)
                return _Outcome.DONE
            outcome = await self._evaluate(batch, batch.rows)
            if outcome is not None:
                return outcome

    async def _evaluate(
        self, batch: _Batch, rows: Sequence[_PendingRow]
    ) -> _Outcome | None:
        """One AI call for `rows`; None means "go on with the next batch".

        An answer that is not a `{"results": [...]}` object is retried one
        post per request (paced), so a poison post only hurts itself.
        """
        await self._pacer.wait()
        self._report.ai_calls += 1
        try:
            evaluation = await evaluate_batch(
                self._groq,
                self._config.model,
                batch.description,
                batch.profile,
                [row.post for row in rows],
            )
        except EvaluationRateLimitedError as exc:
            logger.warning("Groq rate limit, evaluation stops for this run: %s", exc)
            await _set_ai_failing(self._session_factory, self._user_id, self._clock())
            return _Outcome.STOP_RUN
        except EvaluationTransportError as exc:
            logger.warning("Groq unavailable for user %s: %s", self._user_id, exc)
            await _set_ai_failing(self._session_factory, self._user_id, self._clock())
            return _Outcome.STOP_USER
        except EvaluationFormatError as exc:
            if len(rows) > 1:
                logger.warning(
                    "Invalid AI answer for user %s (%s); retrying %d posts one by one",
                    self._user_id,
                    exc,
                    len(rows),
                )
                for row in rows:
                    outcome = await self._evaluate(batch, [row])
                    if outcome is not None:
                        return outcome
                return None
            key = rows[0].post.external_key
            logger.warning("Invalid AI answer for post %s: %s", key, exc)
            evaluation = BatchEvaluation(
                results={}, missing_keys=[key], invalid_keys=[key]
            )

        if evaluation.invalid_keys:
            logger.warning(
                "No valid verdict for %d post(s) of user %s",
                len(evaluation.invalid_keys),
                self._user_id,
            )
        await _apply_evaluation(
            self._session_factory,
            self._user_id,
            rows,
            evaluation,
            self._clock(),
            self._report,
        )
        missing = set(evaluation.missing_keys)
        self._skip_ids.update(
            row.vacancy_id for row in rows if row.post.external_key in missing
        )
        return None


async def _apply_evaluation(
    session_factory: SessionFactory,
    user_id: str,
    rows: Sequence[_PendingRow],
    evaluation: BatchEvaluation,
    now: datetime,
    report: RunReport,
) -> None:
    """Apply verdicts in one short transaction.

    Match → card `new`; no match → card deleted, seen key kept. A post without
    a valid verdict (left out, malformed item, or invalid single-post answer)
    gets one attempt counted; after MAX_EVAL_ATTEMPTS it is treated as rejected.
    """
    evaluated_keys: list[str] = []
    new_ids: list[str] = []
    async with session_factory() as session, session.begin():
        for row in rows:
            verdict = evaluation.results.get(row.post.external_key)
            if verdict is None:
                await _count_failed_attempt(session, row, report)
                continue
            evaluated_keys.append(row.post.external_key)
            if verdict.match and verdict.fit is not None:
                report.matches += 1
                # A repost whose card appeared after this post was stored
                # (e.g. both posts waited in the same run): merge, so the
                # card keeps the first post and the alert counts it once.
                if row.post.job_link is not None and (
                    target_id := await _merge_target(
                        session, user_id, row.post.job_link, exclude_id=row.vacancy_id
                    )
                ):
                    if await _promote_earlier_pending(
                        session, row.vacancy_id, target_id, verdict
                    ):
                        # Alerted only if the replaced card was not yet
                        # (the alert step filters on `alert_handled_at`).
                        new_ids.append(row.vacancy_id)
                    else:
                        await _merge_pending_into(session, row.vacancy_id, target_id)
                    report.posts_merged += 1
                    continue
                result = await session.execute(
                    update(Vacancy)
                    .where(Vacancy.id == row.vacancy_id, Vacancy.state == "pending")
                    .values(
                        state="new",
                        fit=verdict.fit.value,
                        fit_reason=verdict.reason or None,
                        **_named_values(row.post.external_key, verdict),
                    )
                )
                if result.rowcount:
                    new_ids.append(row.vacancy_id)
            else:
                await _delete_pending(session, row.vacancy_id)
        if evaluated_keys:
            await session.execute(
                update(VacancySeenKey)
                .where(
                    VacancySeenKey.user_id == user_id,
                    VacancySeenKey.external_key.in_(evaluated_keys),
                )
                .values(evaluated_at=now)
            )
        # The AI answered, so it is reachable (even if an item was malformed).
        await session.execute(
            update(VacancySearchSettings)
            .where(VacancySearchSettings.user_id == user_id)
            .values(ai_failing_since=None)
        )
    report.posts_evaluated += len(evaluated_keys)
    # After the commit: only cards that really became `new` are alerted.
    report.new_card_ids.setdefault(user_id, []).extend(new_ids)


def _named_values(external_key: str, verdict: PostVerdict) -> dict[str, Any]:
    """Company and title for a rated card.

    Telegram and boards: the stored values win, the AI fills the gaps. Web:
    the AI wins; the stored ones (JobPosting or listing title) are the
    fallback, as listing titles are often noisy.
    """
    if external_key.startswith(_WEB_KEY_PREFIX):
        return {
            "company": verdict.company or Vacancy.company,
            "title": verdict.title or Vacancy.title,
        }
    return {
        "company": func.coalesce(Vacancy.company, verdict.company),
        "title": func.coalesce(Vacancy.title, verdict.title),
    }


async def _count_failed_attempt(
    session: AsyncSession, row: _PendingRow, report: RunReport
) -> None:
    if row.eval_attempts + 1 >= MAX_EVAL_ATTEMPTS:
        logger.warning(
            "Post %s rejected: no valid AI verdict after %d attempts",
            row.post.external_key,
            MAX_EVAL_ATTEMPTS,
        )
        await _delete_pending(session, row.vacancy_id)
        report.rejected += 1
        return
    await session.execute(
        update(Vacancy)
        .where(Vacancy.id == row.vacancy_id, Vacancy.state == "pending")
        .values(eval_attempts=Vacancy.eval_attempts + 1)
    )


async def _delete_pending(session: AsyncSession, vacancy_id: str) -> None:
    """Delete a pending card and its card sources (no FK cascade on SQLite).
    Its seen key stays, so the post never comes back."""
    deleted = await session.execute(
        delete(Vacancy).where(Vacancy.id == vacancy_id, Vacancy.state == "pending")
    )
    if deleted.rowcount:
        await session.execute(
            delete(VacancyCardSource).where(VacancyCardSource.vacancy_id == vacancy_id)
        )


async def _set_ai_failing(
    session_factory: SessionFactory, user_id: str, now: datetime
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            update(VacancySearchSettings)
            .where(VacancySearchSettings.user_id == user_id)
            .values(
                ai_failing_since=func.coalesce(
                    VacancySearchSettings.ai_failing_since, now
                )
            )
        )


async def _set_limit_reached(
    session_factory: SessionFactory, user_id: str, local_date: date
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            update(VacancySearchSettings)
            .where(VacancySearchSettings.user_id == user_id)
            .values(limit_reached_on=local_date)
        )


# --------------------------------------------------------------------------
# Retention
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class CleanupReport:
    cards_deleted: int
    pending_deleted: int
    card_sources_deleted: int


async def cleanup(session_factory: SessionFactory, clock: Clock) -> CleanupReport:
    """Daily retention, one short transaction (no network).

    - `new`/`seen`/`dismissed` cards first fetched more than 30 days ago are
      deleted;
    - `pending` posts older than 7 days are deleted only for users without a
      search description (posts waiting for the AI or the daily cap stay);
    - `added` cards stay while they link to their application; once the
      application is deleted (`application_id` cleared) they are deleted too;
    - seen keys are never deleted, so deleted cards never come back.

    Card sources are deleted explicitly (SQLite does not enforce the FK
    cascade here): after the cards, every card source whose card is gone.
    Deleting cards first keeps this right on PostgreSQL too, where a card
    could change state (e.g. become `added`) between two statements.
    """
    now = clock()
    with_description = select(VacancySearchSettings.user_id).where(
        VacancySearchSettings.description.is_not(None),
        func.trim(VacancySearchSettings.description) != "",
    )
    async with session_factory() as session, session.begin():
        cards = await session.execute(
            delete(Vacancy).where(
                or_(
                    and_(
                        Vacancy.state.in_(_VISIBLE_STATES),
                        Vacancy.found_at < now - CARD_RETENTION,
                    ),
                    and_(Vacancy.state == "added", Vacancy.application_id.is_(None)),
                )
            )
        )
        pending = await session.execute(
            delete(Vacancy).where(
                Vacancy.state == "pending",
                Vacancy.found_at < now - PENDING_WITHOUT_DESCRIPTION_RETENTION,
                Vacancy.user_id.not_in(with_description),
            )
        )
        orphans = await session.execute(
            delete(VacancyCardSource).where(
                ~select(Vacancy.id)
                .where(Vacancy.id == VacancyCardSource.vacancy_id)
                .exists()
            )
        )
    report = CleanupReport(
        cards_deleted=cards.rowcount,
        pending_deleted=pending.rowcount,
        card_sources_deleted=orphans.rowcount,
    )
    logger.info(
        "Discovery cleanup: cards deleted=%d, pending deleted=%d, "
        "card sources deleted=%d",
        report.cards_deleted,
        report.pending_deleted,
        report.card_sources_deleted,
    )
    return report


def _log_report(name: str, report: RunReport) -> None:
    logger.info(
        "Discovery %s: sources read=%d failed=%d, posts stored=%d excluded=%d "
        "merged=%d, AI calls=%d evaluated=%d matches=%d rejected=%d, "
        "users at daily cap=%d, alerts sent=%d",
        name,
        report.sources_read,
        report.sources_failed,
        report.posts_stored,
        report.posts_excluded,
        report.posts_merged,
        report.ai_calls,
        report.posts_evaluated,
        report.matches,
        report.rejected,
        len(report.users_capped),
        report.alerts_sent,
    )
