"""Discovery runs: read sources, store new posts, evaluate them with AI.

INVARIANT (shared SQLite file with the API and the bot): no network I/O while a
database transaction is open. Every step is either
- read: a short session that loads plain data and closes, or
- network: an HTTP fetch or a Groq call with no session open, or
- write: a short `session.begin()` block that commits on exit.
Functions never hold an ORM object across a network call; they copy what they
need into the frozen dataclasses below.

Scope today: Telegram sources. Slots for later slices are marked with TODO.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum, auto
from typing import Any, Self, TypeAlias

import groq
import httpx
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.timezones import local_day_bounds, zone_or_utc
from app.discovery.evaluator import (
    BATCH_SIZE,
    BatchEvaluation,
    EvaluationFormatError,
    EvaluationRateLimitedError,
    EvaluationTransportError,
    evaluate_batch,
)
from app.discovery.fetchers.telegram import SourceReadError, fetch_channel_posts
from app.discovery.prefilter import excluded
from app.discovery.types import RawPost
from app.models.user import User
from app.models.vacancy import Vacancy, VacancyCardSource
from app.models.vacancy_search_settings import VacancySearchSettings
from app.models.vacancy_seen_key import VacancySeenKey
from app.models.vacancy_source import VacancySource

__all__ = [
    "EVAL_PAUSE_S",
    "LOOKBACK",
    "MAX_EVAL_ATTEMPTS",
    "MAX_PAGES",
    "READ_ERROR_MESSAGES",
    "Clock",
    "DiscoveryConfig",
    "RunReport",
    "check_all",
    "evaluate_pending",
    "run_initial_scans",
]

logger = logging.getLogger(__name__)

LOOKBACK = timedelta(days=7)
MAX_PAGES = 10
EVAL_PAUSE_S = 30.0
MAX_EVAL_ATTEMPTS = 3
# Seen keys of posts inside the lookback window were first seen inside it too
# (a post cannot be seen before it is posted); the margin absorbs clock skew.
_KNOWN_KEYS_MARGIN = timedelta(days=1)

READ_ERROR_MESSAGES = {
    "private_or_deleted": "Channel is private or deleted",
    "unreachable": "Could not reach the source",
}

SessionFactory: TypeAlias = Callable[[], AsyncSession]
# Returns the current time as naive UTC. Called per source and per AI batch,
# so long runs (30 s between batches) keep real timestamps and local days.
Clock: TypeAlias = Callable[[], datetime]
SleepFn: TypeAlias = Callable[[float], Awaitable[None]]


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
    ai_calls: int = 0
    posts_evaluated: int = 0
    matches: int = 0
    rejected: int = 0
    users_capped: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True, kw_only=True)
class _SourceRef:
    id: str
    user_id: str
    kind: str
    handle: str
    display_name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class _PendingRow:
    vacancy_id: str
    eval_attempts: int
    post: RawPost


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
) -> RunReport:
    """First 7-day scan of every source whose first scan has not completed and
    is due (`next_initial_attempt_at` unset or passed), then evaluate the
    pending posts of the users whose sources were scanned.
    """
    config = config or DiscoveryConfig.from_settings()
    report = RunReport()
    sources = await _load_sources(session_factory, clock(), initial=True)
    for source in sources:
        await _scan_source(
            session_factory,
            http_client,
            source,
            clock(),
            report,
            initial=True,
            sleep=sleep,
        )
    if sources:
        await evaluate_pending(
            session_factory,
            groq_client,
            clock,
            user_ids={source.user_id for source in sources},
            config=config,
            sleep=sleep,
            report=report,
        )
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
) -> RunReport:
    """Hourly check: read every source with a completed first scan, store new
    posts, then evaluate the pending posts of every user with a description.

    Sources still in their first scan are skipped. One failing source does not
    stop the run.
    """
    config = config or DiscoveryConfig.from_settings()
    report = RunReport()
    for source in await _load_sources(session_factory, clock(), initial=False):
        await _scan_source(
            session_factory,
            http_client,
            source,
            clock(),
            report,
            initial=False,
            sleep=sleep,
        )
    await evaluate_pending(
        session_factory, groq_client, clock, config=config, sleep=sleep, report=report
    )
    # TODO(Slice 7): send alerts for cards that became `new` in this run.
    _log_report("hourly check", report)
    return report


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
    # TODO(Slice 6): greenhouse / lever / lever_eu fetchers.
    stmt = select(VacancySource).where(VacancySource.kind == "telegram")
    if initial:
        stmt = stmt.where(
            VacancySource.initial_scan_completed_at.is_(None),
            (VacancySource.next_initial_attempt_at.is_(None))
            | (VacancySource.next_initial_attempt_at <= now),
        )
    else:
        stmt = stmt.where(VacancySource.initial_scan_completed_at.is_not(None))
    stmt = stmt.order_by(VacancySource.created_at, VacancySource.id)
    async with session_factory() as session:
        sources = (await session.scalars(stmt)).all()
        return [
            _SourceRef(
                id=s.id,
                user_id=s.user_id,
                kind=s.kind,
                handle=s.handle,
                display_name=s.display_name,
            )
            for s in sources
        ]


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
    cutoff = now - LOOKBACK
    # The first scan stores every post of the window that is not yet a seen
    # key (filtered at insert), so a re-added source skips what it showed before.
    known = set() if initial else await _recent_keys(session_factory, source, cutoff)
    try:
        posts = await fetch_channel_posts(
            http_client, source.handle, known, cutoff, MAX_PAGES, sleep=sleep
        )
    except SourceReadError as exc:
        logger.warning("Source %s could not be read: %s", source.id, exc)
        await _record_read_failure(
            session_factory, source, READ_ERROR_MESSAGES[exc.reason], now, initial
        )
        report.sources_failed += 1
        return
    except ValueError:  # handle no longer passes validation
        logger.warning("Source %s has an invalid handle", source.id)
        await _record_read_failure(
            session_factory, source, READ_ERROR_MESSAGES["unreachable"], now, initial
        )
        report.sources_failed += 1
        return
    await _store_posts(session_factory, source, posts, now, report, initial=initial)


def _next_initial_attempt(now: datetime) -> datetime | None:
    """When a failed first scan is retried.

    TODO(Slice 8): backoff 1, 5, 15 min, then hourly. For now: the next
    every-minute run (None = due immediately).
    """
    del now
    return None


async def _record_read_failure(
    session_factory: SessionFactory,
    source: _SourceRef,
    message: str,
    now: datetime,
    initial: bool,
) -> None:
    values: dict[str, Any] = {
        "failing_since": func.coalesce(VacancySource.failing_since, now),
        "last_error": message,
    }
    if initial:
        values["next_initial_attempt_at"] = _next_initial_attempt(now)
    async with session_factory() as session, session.begin():
        await session.execute(
            update(VacancySource).where(VacancySource.id == source.id).values(**values)
        )


async def _store_posts(
    session_factory: SessionFactory,
    source: _SourceRef,
    posts: Sequence[RawPost],
    now: datetime,
    report: RunReport,
    *,
    initial: bool,
) -> None:
    """Record seen keys and insert `pending` cards in one short transaction."""
    values: dict[str, Any] = {
        "last_checked_at": now,
        "failing_since": None,
        "last_error": None,
    }
    if initial:
        values |= {"initial_scan_completed_at": now, "next_initial_attempt_at": None}

    async with session_factory() as session, session.begin():
        # Update the source first: if it was deleted during the fetch, nothing
        # is stored (removal stops the scan). The UPDATE also takes the write
        # lock, so a concurrent delete waits for this transaction.
        result = await session.execute(
            update(VacancySource).where(VacancySource.id == source.id).values(**values)
        )
        if result.rowcount == 0:
            logger.info("Source %s was removed during its scan", source.id)
            return
        report.sources_read += 1
        if not posts:
            return

        exclude_terms: list[str] = (
            await session.scalar(
                select(VacancySearchSettings.exclude_terms).where(
                    VacancySearchSettings.user_id == source.user_id
                )
            )
            or []
        )
        keys = [post.external_key for post in posts]
        seen = set(
            (
                await session.scalars(
                    select(VacancySeenKey.external_key).where(
                        VacancySeenKey.user_id == source.user_id,
                        VacancySeenKey.external_key.in_(keys),
                    )
                )
            ).all()
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
            # TODO(Slice 8): merge into an existing new/seen/dismissed card with
            # the same job_link instead of creating a new one.
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
            .where(Vacancy.user_id == user_id, Vacancy.state == "pending")
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
    async with session_factory() as session, session.begin():
        for row in rows:
            verdict = evaluation.results.get(row.post.external_key)
            if verdict is None:
                await _count_failed_attempt(session, row, report)
                continue
            evaluated_keys.append(row.post.external_key)
            if verdict.match and verdict.fit is not None:
                await session.execute(
                    update(Vacancy)
                    .where(Vacancy.id == row.vacancy_id, Vacancy.state == "pending")
                    .values(
                        state="new",
                        fit=verdict.fit.value,
                        fit_reason=verdict.reason or None,
                        company=func.coalesce(Vacancy.company, verdict.company),
                        title=func.coalesce(Vacancy.title, verdict.title),
                    )
                )
                report.matches += 1
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


def _log_report(name: str, report: RunReport) -> None:
    logger.info(
        "Discovery %s: sources read=%d failed=%d, posts stored=%d excluded=%d, "
        "AI calls=%d evaluated=%d matches=%d rejected=%d, users at daily cap=%d",
        name,
        report.sources_read,
        report.sources_failed,
        report.posts_stored,
        report.posts_excluded,
        report.ai_calls,
        report.posts_evaluated,
        report.matches,
        report.rejected,
        len(report.users_capped),
    )
