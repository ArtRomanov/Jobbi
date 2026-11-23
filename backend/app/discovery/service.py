"""Discovery runs: read sources, store new posts, evaluate them with AI.

INVARIANT (shared SQLite file with the API and the bot): no network I/O while a
database transaction is open. Every step is either
- read: a short session that loads plain data and closes, or
- network: an HTTP fetch or a Groq call with no session open, or
- write: a short `session.begin()` block that commits on exit.
Functions never hold an ORM object across a network call; they copy what they
need into the frozen dataclasses below.

Sources: Telegram channels and Greenhouse / Lever boards (`board_scan`).

Reposts (same `job_link` as a user's `new`/`seen`/`dismissed` card) merge into
that card as an extra `vacancy_card_sources` row. Mostly at store time, before
any AI call: the card keeps the first post's date, fit and text anyway, so
rating the repost would only spend the daily cap. Posts stored before their
card existed (e.g. two channels in one run, both pending) merge after a match.

Digests (spec 012): a post the AI rates as several vacancies becomes one card
per matching vacancy (`<post key>#<n>`, its lines of the post as the text, the
first outside link on those lines as the job link); a vacancy whose job link
is already on a card merges into it. The pending row of the post is deleted.
A post with several outside links is never merged at store time: it may be a
digest whose first link is only one of its vacancies (a single post with
several links merges after rating instead).

Forwarded posts (spec 012, 2.2) are never merged at store time; they are rated
like channel posts, and each rated one gets a `ForwardResult` in the run
report, sent as the bot's reply after the run (`forward_replies`).
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
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot

from app.core.config import Settings, get_settings
from app.core.timezones import local_day_bounds, zone_or_utc
from app.discovery.alerts import send_run_alerts
from app.discovery.board_scan import BOARD_KINDS, board_key_prefix, fetch_board
from app.discovery.evaluator import (
    BATCH_SIZE,
    MAX_DIGEST_VACANCIES,
    MAX_POST_CHARS,
    BatchEvaluation,
    EvaluationFormatError,
    EvaluationRateLimitedError,
    EvaluationTransportError,
    PostVerdict,
    VacancyItem,
    batch_take,
    can_be_digest,
    evaluate_batch,
    fragment,
    is_cut,
)
from app.discovery.fetchers.errors import BoardReadError
from app.discovery.fetchers.telegram import SourceReadError, fetch_channel_posts
from app.discovery.forward_replies import (
    ForwardResult,
    ForwardResultKind,
    send_forward_replies,
)
from app.discovery.types import PostLink, RawPost
from app.models.forwarded_post import ForwardedPost
from app.models.user import User
from app.models.vacancy import Vacancy, VacancyCardSource
from app.models.vacancy_search_settings import VacancySearchSettings
from app.models.vacancy_seen_key import VacancySeenKey
from app.models.vacancy_source import VacancySource

__all__ = [
    "CARD_RETENTION",
    "EVAL_PAUSE_S",
    "FORWARDED_KIND",
    "FORWARDED_POST_RETENTION",
    "LOOKBACK",
    "MAX_EVAL_ATTEMPTS",
    "MAX_PAGES",
    "PENDING_WITHOUT_DESCRIPTION_RETENTION",
    "READ_ERROR_MESSAGES",
    "CleanupReport",
    "Clock",
    "DiscoveryConfig",
    "ForwardOutcome",
    "ForwardedChannel",
    "RunReport",
    "check_all",
    "cleanup",
    "evaluate_pending",
    "run_initial_scans",
    "store_forwarded_post",
]

logger = logging.getLogger(__name__)

LOOKBACK = timedelta(days=7)
MAX_PAGES = 10
# One AI call per pause. gpt-oss-20b spends ~4 000-5 000 tokens per batch of 5,
# so 30 s (two calls a minute) would exceed the 8 000 tokens/minute account limit.
EVAL_PAUSE_S = 45.0
MAX_EVAL_ATTEMPTS = 3
# Length of the `external_key` columns; a digest card's `<post key>#<n>` must fit.
MAX_EXTERNAL_KEY_CHARS = 255
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
FORWARDED_POST_RETENTION = timedelta(days=30)
# States a repost can merge into (and that retention deletes after 30 days).
_VISIBLE_STATES = ("new", "seen", "dismissed")

# Keyed by `SourceReadError.reason` (Telegram) and `BoardReadError.reason`.
READ_ERROR_MESSAGES = {
    "private_or_deleted": "Channel is private or deleted",
    "not_found": "Job board not found",
    "unreachable": "Could not reach the source",
}
SUPPORTED_KINDS = frozenset({"telegram"}) | BOARD_KINDS
# Card-source kind of posts the user forwarded to the bot. Not a
# `VacancySource` kind: nothing is ever fetched for it.
FORWARDED_KIND = "tg_forward"

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
    # Reposts added as a source to an existing card (at store or after rating).
    posts_merged: int = 0
    ai_calls: int = 0
    posts_evaluated: int = 0
    # Evaluated posts longer than the AI window (their end was not read).
    posts_cut: int = 0
    matches: int = 0
    rejected: int = 0
    users_capped: set[str] = field(default_factory=set)
    # Cards that became `new` in this run, per user (input for alerts).
    new_card_ids: dict[str, list[str]] = field(default_factory=dict)
    alerts_sent: int = 0
    # Rated posts the user forwarded to the bot (input for the bot's replies).
    forward_results: list[ForwardResult] = field(default_factory=list)
    forward_replies_sent: int = 0


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
    bot: Bot | None = None,
) -> RunReport:
    """First 7-day scan of every source whose first scan has not completed and
    is due (`next_initial_attempt_at` unset or passed), then evaluate the
    pending posts of the users whose sources were scanned or who forwarded a
    post to the bot (so a forwarded post is rated within about a minute).

    First-scan cards are never alerted. Posts of those users that were found
    by an earlier hourly check and waited (daily cap, AI down) may be rated
    here; they are alerted at the end, like in `check_all`.
    """
    config = config or DiscoveryConfig.from_settings()
    report = RunReport()
    sources = await _load_sources(session_factory, clock(), initial=True)
    user_ids = {source.user_id for source in sources}
    user_ids |= await _users_with_forwarded_pending(session_factory, clock())
    if not user_ids:
        return report

    async def work() -> None:
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
        await evaluate_pending(
            session_factory,
            groq_client,
            clock,
            user_ids=user_ids,
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
) -> RunReport:
    """Hourly check: read every source with a completed first scan, store new
    posts, then evaluate the pending posts of every user with a description.

    Sources still in their first scan are skipped. One failing source does not
    stop the run. At the end each user gets one Telegram alert (when `bot` is
    given and the user linked Telegram) for the cards that became `new` in
    this run, first-scan cards excluded.
    """
    config = config or DiscoveryConfig.from_settings()
    report = RunReport()

    async def work() -> None:
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
    """Run `work`, then alert about the cards it made `new` and reply about
    the forwarded posts it rated — also when it fails half way, so those
    cards are not left unannounced with `alert_handled_at` NULL forever.

    - Success or an ordinary exception: alert and reply normally, then
      re-raise.
    - Cancellation (worker shutting down), also while the alert itself is
      being sent: no network — the cards are only marked handled (one short
      write), then the cancellation goes on. They stay in the Inbox; they are
      just not announced. Forward replies not sent yet keep `reported_at`
      NULL (nothing is written for them).
    """
    try:
        await work
    except asyncio.CancelledError:
        await _alert_safely(session_factory, None, clock, report, sleep)
        raise
    except Exception:
        await _alert_safely(session_factory, bot, clock, report, sleep)
        await _reply_safely(session_factory, bot, clock, report, sleep)
        raise
    try:
        report.alerts_sent = await send_run_alerts(
            session_factory, bot, report.new_card_ids, clock, sleep=sleep
        )
    except asyncio.CancelledError:
        # Cards already announced are handled; this marks the rest.
        await _alert_safely(session_factory, None, clock, report, sleep)
        raise
    report.forward_replies_sent = await send_forward_replies(
        session_factory, bot, report.forward_results, clock, sleep=sleep
    )


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


async def _reply_safely(
    session_factory: SessionFactory,
    bot: Bot | None,
    clock: Clock,
    report: RunReport,
    sleep: SleepFn,
) -> None:
    """Forward replies on the failure path: never hide the original error."""
    try:
        report.forward_replies_sent = await send_forward_replies(
            session_factory, bot, report.forward_results, clock, sleep=sleep
        )
    except Exception:
        logger.exception("Forward replies after an interrupted run failed")


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
    except ValueError:  # handle no longer passes validation
        logger.warning("Source %s has an invalid handle", source.id)
        await _record_read_failure(
            session_factory, source, READ_ERROR_MESSAGES["unreachable"], now, initial
        )
        report.sources_failed += 1
        return
    await _store_posts(
        session_factory,
        source,
        posts,
        now,
        report,
        initial=initial,
        seen_only_keys=seen_only_keys,
    )


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
    seen_only_keys: Sequence[str] = (),
) -> None:
    """Record seen keys and insert `pending` cards in one short transaction.

    `seen_only_keys` (board initial scan: jobs outside the window) are only
    recorded as seen, so they never become cards later.
    """
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
        if not posts and not seen_only_keys:
            return

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
            # A repost of a job already on a card: add this source to that card
            # (no AI call; the card keeps the first post's date, fit and text).
            if (
                post.job_link is not None
                # Several different links: maybe a digest, merged per vacancy
                # after rating. One link repeated on several lines is one job.
                and len({link.url for link in post.links}) <= 1
                and (
                    target_id := await _merge_target(
                        session, source.user_id, post.job_link
                    )
                )
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
                    links=_links_to_json(post.links),
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


class ForwardOutcome(Enum):
    ADDED = auto()  # new pending card; rated by the next per-minute run
    ALREADY_SEEN = auto()  # this post was found or forwarded before


@dataclass(frozen=True, slots=True, kw_only=True)
class ForwardedChannel:
    """Card-source identity of a channel a post was forwarded from.

    `handle` is the channel's username (lowercased) or `c<internal id>` for a
    private channel; `label` is the channel title shown on the card.
    """

    handle: str
    label: str


async def store_forwarded_post(
    session_factory: SessionFactory,
    user_id: str,
    channel: ForwardedChannel,
    post: RawPost,
    now: datetime,
    *,
    chat_id: int,
    message_id: int,
) -> ForwardOutcome:
    """Put a post the user forwarded to the bot into their Inbox as `pending`,
    and remember where to reply with its rating result (`forwarded_posts`).

    Unlike `_store_posts` there is no alert (the user already knows about it)
    and no merge at store time: the post may be a digest, and a single post
    merges into a card with its job link after rating, like a channel post.
    `chat_id`/`message_id`: the user's chat with the bot and the forwarded
    message in it.
    """
    try:
        async with session_factory() as session, session.begin():
            if await _already_seen(session, user_id, [post.external_key]):
                # Fetched from a watched channel and not rated yet: the user
                # has seen it now, so it is not alerted later.
                await session.execute(
                    update(Vacancy)
                    .where(
                        Vacancy.user_id == user_id,
                        Vacancy.external_key == post.external_key,
                        Vacancy.alert_handled_at.is_(None),
                    )
                    .values(alert_handled_at=now)
                )
                return ForwardOutcome.ALREADY_SEEN
            session.add(
                VacancySeenKey(
                    user_id=user_id, external_key=post.external_key, first_seen_at=now
                )
            )
            session.add(
                ForwardedPost(
                    user_id=user_id,
                    external_key=post.external_key,
                    chat_id=chat_id,
                    message_id=message_id,
                    created_at=now,
                )
            )
            vacancy_id = str(uuid.uuid4())
            session.add(
                Vacancy(
                    id=vacancy_id,
                    user_id=user_id,
                    source_id=None,
                    external_key=post.external_key,
                    url=post.url,
                    job_link=post.job_link,
                    title=post.title,
                    company=post.company,
                    text=post.text,
                    links=_links_to_json(post.links),
                    posted_at=post.posted_at,
                    found_at=now,
                    state="pending",
                    from_initial_scan=False,
                    alert_handled_at=now,
                )
            )
            session.add(
                VacancyCardSource(
                    vacancy_id=vacancy_id,
                    source_id=None,
                    source_kind=FORWARDED_KIND,
                    source_handle=channel.handle,
                    label=channel.label,
                )
            )
            return ForwardOutcome.ADDED
    except IntegrityError:
        # The same post forwarded twice at once: the other one won.
        return ForwardOutcome.ALREADY_SEEN


def _links_to_json(links: Sequence[PostLink]) -> list[list[Any]] | None:
    """`Vacancy.links` value: `[[line, url], ...]`, NULL when there are none."""
    return [[link.line, link.url] for link in links] or None


def _links_from_json(value: object) -> tuple[PostLink, ...]:
    """`RawPost.links` from a stored `Vacancy.links` (NULL or malformed → none)."""
    if not isinstance(value, list):
        return ()
    links: list[PostLink] = []
    for item in value:
        match item:
            case [int(line), str(url)] if not isinstance(line, bool):
                links.append(PostLink(line=line, url=url))
            case _:
                continue
    return tuple(links)


async def _users_with_forwarded_pending(
    session_factory: SessionFactory, now: datetime
) -> set[str]:
    """Users with a forwarded post waiting for its first rating attempt, whose
    AI is not failing and who did not hit the daily cap lately.

    Anything else (a retry, AI down, cap) is left to the hourly check, so the
    per-minute run neither calls a failing AI every minute nor burns the
    MAX_EVAL_ATTEMPTS meant for hourly retries in three minutes. The cap
    check is by UTC date with a day of slack (the cap day is the user's
    local date); a skipped user is still rated hourly.
    """
    async with session_factory() as session:
        rows = await session.scalars(
            select(Vacancy.user_id)
            .join(VacancyCardSource, VacancyCardSource.vacancy_id == Vacancy.id)
            .join(
                VacancySearchSettings,
                VacancySearchSettings.user_id == Vacancy.user_id,
            )
            .where(
                Vacancy.state == "pending",
                Vacancy.eval_attempts == 0,
                VacancyCardSource.source_kind == FORWARDED_KIND,
                VacancySearchSettings.description.is_not(None),
                VacancySearchSettings.ai_failing_since.is_(None),
                or_(
                    VacancySearchSettings.limit_reached_on.is_(None),
                    VacancySearchSettings.limit_reached_on
                    < now.date() - timedelta(days=1),
                ),
            )
            .distinct()
        )
        return set(rows.all())


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
            company=func.coalesce(Vacancy.company, verdict.company),
            title=func.coalesce(Vacancy.title, verdict.title),
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
        # Size-based batch: the leading posts whose windowed text fits the
        # character budget (always at least one).
        posts = [_raw_post(row) for row in rows]
        take = batch_take(posts)
        rows, posts = rows[:take], posts[:take]
        return _Batch(
            description=description,
            profile=_profile(user),
            rows=[
                _PendingRow(
                    vacancy_id=row.id,
                    eval_attempts=row.eval_attempts,
                    post=post,
                )
                for row, post in zip(rows, posts, strict=True)
            ],
        )


def _raw_post(row: Vacancy) -> RawPost:
    return RawPost(
        external_key=row.external_key,
        url=row.url,
        job_link=row.job_link,
        title=row.title,
        company=row.company,
        text=row.text,
        posted_at=row.posted_at,
        links=_links_from_json(row.links),
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

    Match → card `new`; no match → card deleted, seen key kept. A digest
    becomes one card per matching vacancy (`_split_digest`). A post without a
    valid verdict (left out, malformed item, or invalid single-post answer)
    gets one attempt counted; after MAX_EVAL_ATTEMPTS it is treated as
    rejected. Forwarded posts follow the same rules; each one with an
    unreported `forwarded_posts` row gets a `ForwardResult` in the report.
    """
    evaluated_keys: list[str] = []
    cut_keys: list[str] = []
    new_ids: list[str] = []
    results: list[ForwardResult] = []
    async with session_factory() as session, session.begin():
        forwarded = await _unreported_forwards(
            session, user_id, [row.post.external_key for row in rows]
        )
        for row in rows:
            key = row.post.external_key
            verdict = evaluation.results.get(key)
            if verdict is None:
                is_rejected = await _count_failed_attempt(session, row, report)
                if is_rejected and key in forwarded:
                    results.append(
                        ForwardResult(
                            user_id=user_id,
                            external_key=key,
                            kind=ForwardResultKind.UNRATABLE,
                        )
                    )
                continue
            if is_cut(row.post):
                cut_keys.append(key)
            else:
                evaluated_keys.append(key)
            row_new_ids, result = await _apply_verdict(
                session, user_id, row, verdict, report
            )
            new_ids.extend(row_new_ids)
            if result is not None and key in forwarded:
                results.append(result)
        for keys, values in (
            (evaluated_keys, {"evaluated_at": now}),
            (cut_keys, {"evaluated_at": now, "cut_for_ai": True}),
        ):
            if keys:
                await session.execute(
                    update(VacancySeenKey)
                    .where(
                        VacancySeenKey.user_id == user_id,
                        VacancySeenKey.external_key.in_(keys),
                    )
                    .values(**values)
                )
        # The AI answered, so it is reachable (even if an item was malformed).
        await session.execute(
            update(VacancySearchSettings)
            .where(VacancySearchSettings.user_id == user_id)
            .values(ai_failing_since=None)
        )
    report.posts_evaluated += len(evaluated_keys) + len(cut_keys)
    report.posts_cut += len(cut_keys)
    lengths = {row.post.external_key: len(row.post.text) for row in rows}
    for key in cut_keys:
        logger.warning(
            "Post %s is %d characters long; the AI read only the first %d",
            key,
            lengths[key],
            MAX_POST_CHARS,
        )
    # After the commit: only cards that really became `new` are alerted, and
    # only results that were really stored are replied about.
    report.new_card_ids.setdefault(user_id, []).extend(new_ids)
    report.forward_results.extend(results)


async def _unreported_forwards(
    session: AsyncSession, user_id: str, keys: Sequence[str]
) -> set[str]:
    """Which of `keys` are forwarded posts whose result was not replied yet."""
    if not keys:
        return set()
    return set(
        (
            await session.scalars(
                select(ForwardedPost.external_key).where(
                    ForwardedPost.user_id == user_id,
                    ForwardedPost.external_key.in_(list(keys)),
                    ForwardedPost.reported_at.is_(None),
                )
            )
        ).all()
    )


async def _apply_verdict(
    session: AsyncSession,
    user_id: str,
    row: _PendingRow,
    verdict: PostVerdict,
    report: RunReport,
) -> tuple[list[str], ForwardResult | None]:
    """Apply one post's verdict: (ids of cards that became `new`, the result
    to reply with if the post was forwarded; None when the pending row was
    gone meanwhile)."""
    key = row.post.external_key

    def result(kind: ForwardResultKind, **fields: Any) -> ForwardResult:
        return ForwardResult(user_id=user_id, external_key=key, kind=kind, **fields)

    # Only Telegram posts can be digests; the evaluator already rates any other
    # post as a single one, this is the belt to its braces.
    if verdict.is_digest and can_be_digest(key):
        split = await _split_digest(session, user_id, row, verdict, report)
        if split is None:
            return [], None
        matched = len(split.new_ids) + split.merged
        if not matched:
            return [], result(ForwardResultKind.NONE)
        return split.new_ids, result(
            ForwardResultKind.DIGEST,
            matched=matched,
            total=max(verdict.vacancy_count or 0, matched),
        )
    if not (verdict.match and verdict.fit is not None):
        await _delete_pending(session, row.vacancy_id)
        return [], result(
            ForwardResultKind.NOT_VACANCY
            if verdict.is_vacancy is False
            else ForwardResultKind.NONE
        )

    report.matches += 1
    # A repost whose card appeared after this post was stored (e.g. both
    # posts waited in the same run, or a forwarded post): merge, so the card
    # keeps the first post and the alert counts it once.
    if row.post.job_link is not None and (
        target_id := await _merge_target(
            session, user_id, row.post.job_link, exclude_id=row.vacancy_id
        )
    ):
        target = (
            await session.execute(
                select(Vacancy.title, Vacancy.company).where(Vacancy.id == target_id)
            )
        ).one()
        merged = result(
            ForwardResultKind.MERGED,
            title=target.title or verdict.title,
            company=target.company or verdict.company,
        )
        report.posts_merged += 1
        if await _promote_earlier_pending(session, row.vacancy_id, target_id, verdict):
            # Alerted only if the replaced card was not yet (the alert step
            # filters on `alert_handled_at`).
            return [row.vacancy_id], merged
        await _merge_pending_into(session, row.vacancy_id, target_id)
        return [], merged
    updated = await session.execute(
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
    if not updated.rowcount:
        return [], None
    return [row.vacancy_id], result(
        ForwardResultKind.MATCHED,
        fit=verdict.fit.value,
        title=row.post.title or verdict.title,
        company=row.post.company or verdict.company,
    )


def _item_job_link(post: RawPost, item: VacancyItem) -> str | None:
    """The first outside link of the post on the vacancy's lines."""
    start, end = item.lines
    return next((link.url for link in post.links if start <= link.line <= end), None)


@dataclass(frozen=True, slots=True)
class _DigestSplit:
    new_ids: list[str]  # cards created
    merged: int  # vacancies merged into existing cards


async def _split_digest(
    session: AsyncSession,
    user_id: str,
    row: _PendingRow,
    verdict: PostVerdict,
    report: RunReport,
) -> _DigestSplit | None:
    """Turn a rated digest into one `new` card per matching vacancy, then
    delete its pending row (the post's seen key stays). None when the pending
    row was gone meanwhile (e.g. its source was deleted).

    Each card is `<post key>#<n>` (`n` = the vacancy's 1-based position in the
    AI answer) with the vacancy's lines as its text and the first outside link
    on them as its job link; the rest (source, post link, dates, alert state,
    card sources) is copied from the pending row. A vacancy whose job link is
    already on a visible card adds the post's sources to that card instead.
    Zero matching vacancies just delete the pending row. A card key that
    would not fit the column (unreachable for Telegram keys, which are short)
    skips that vacancy.
    """
    pending = await session.get(Vacancy, row.vacancy_id)
    if pending is None or pending.state != "pending":
        return None
    card_sources = (
        await session.scalars(
            select(VacancyCardSource).where(
                VacancyCardSource.vacancy_id == row.vacancy_id
            )
        )
    ).all()
    new_ids: list[str] = []
    merged = 0
    for n, item in enumerate(verdict.vacancies[:MAX_DIGEST_VACANCIES], start=1):
        card_key = f"{row.post.external_key}#{n}"
        if len(card_key) > MAX_EXTERNAL_KEY_CHARS:
            logger.warning(
                "Digest %s: card key for vacancy %d is too long; skipped",
                row.post.external_key,
                n,
            )
            continue
        text = fragment(row.post.text, item.lines)
        if not text:
            logger.warning(
                "Digest %s: vacancy %d points at blank lines %s; skipped",
                row.post.external_key,
                n,
                item.lines,
            )
            continue
        job_link = _item_job_link(row.post, item)
        if job_link is not None and (
            target_id := await _merge_target(session, user_id, job_link)
        ):
            await _copy_card_sources(session, card_sources, target_id)
            report.posts_merged += 1
            merged += 1
            continue
        card_id = str(uuid.uuid4())
        session.add(
            Vacancy(
                id=card_id,
                user_id=pending.user_id,
                source_id=pending.source_id,
                external_key=card_key,
                url=pending.url,
                job_link=job_link,
                title=item.title,
                company=item.company,
                text=text,
                posted_at=pending.posted_at,
                found_at=pending.found_at,
                state="new",
                fit=item.fit.value,
                fit_reason=item.reason[:255] or None,
                from_initial_scan=pending.from_initial_scan,
                alert_handled_at=pending.alert_handled_at,
            )
        )
        await _copy_card_sources(session, card_sources, card_id)
        # Flushed now, so a later vacancy of this digest with the same job
        # link merges into this card.
        await session.flush()
        new_ids.append(card_id)
        report.matches += 1
    await _delete_pending(session, row.vacancy_id)
    return _DigestSplit(new_ids=new_ids, merged=merged)


async def _copy_card_sources(
    session: AsyncSession,
    card_sources: Sequence[VacancyCardSource],
    vacancy_id: str,
) -> None:
    """List copies of `card_sources` on a card, once per source identity."""
    for card_source in card_sources:
        if await _has_card_source(
            session, vacancy_id, card_source.source_kind, card_source.source_handle
        ):
            continue
        session.add(
            VacancyCardSource(
                vacancy_id=vacancy_id,
                source_id=card_source.source_id,
                source_kind=card_source.source_kind,
                source_handle=card_source.source_handle,
                label=card_source.label,
            )
        )


async def _count_failed_attempt(
    session: AsyncSession, row: _PendingRow, report: RunReport
) -> bool:
    """Count one failed attempt; True when this was the last one and the post
    was deleted (rejected)."""
    if row.eval_attempts + 1 >= MAX_EVAL_ATTEMPTS:
        logger.warning(
            "Post %s rejected: no valid AI verdict after %d attempts",
            row.post.external_key,
            MAX_EVAL_ATTEMPTS,
        )
        await _delete_pending(session, row.vacancy_id)
        report.rejected += 1
        return True
    await session.execute(
        update(Vacancy)
        .where(Vacancy.id == row.vacancy_id, Vacancy.state == "pending")
        .values(eval_attempts=Vacancy.eval_attempts + 1)
    )
    return False


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
    forwarded_posts_deleted: int


async def cleanup(session_factory: SessionFactory, clock: Clock) -> CleanupReport:
    """Daily retention, one short transaction (no network).

    - `new`/`seen`/`dismissed` cards first fetched more than 30 days ago are
      deleted;
    - `pending` posts older than 7 days are deleted only for users without a
      search description (posts waiting for the AI or the daily cap stay);
    - `added` cards stay while they link to their application; once the
      application is deleted (`application_id` cleared) they are deleted too;
    - seen keys are never deleted, so deleted cards never come back;
    - `forwarded_posts` rows (where to reply about a forwarded post) are
      deleted 30 days after the forward, replied or not.

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
        forwards = await session.execute(
            delete(ForwardedPost).where(
                ForwardedPost.created_at < now - FORWARDED_POST_RETENTION
            )
        )
    report = CleanupReport(
        cards_deleted=cards.rowcount,
        pending_deleted=pending.rowcount,
        card_sources_deleted=orphans.rowcount,
        forwarded_posts_deleted=forwards.rowcount,
    )
    logger.info(
        "Discovery cleanup: cards deleted=%d, pending deleted=%d, "
        "card sources deleted=%d, forwarded posts deleted=%d",
        report.cards_deleted,
        report.pending_deleted,
        report.card_sources_deleted,
        report.forwarded_posts_deleted,
    )
    return report


def _log_report(name: str, report: RunReport) -> None:
    logger.info(
        "Discovery %s: sources read=%d failed=%d, posts stored=%d "
        "merged=%d, AI calls=%d evaluated=%d cut=%d matches=%d rejected=%d, "
        "users at daily cap=%d, alerts sent=%d, forward replies sent=%d",
        name,
        report.sources_read,
        report.sources_failed,
        report.posts_stored,
        report.posts_merged,
        report.ai_calls,
        report.posts_evaluated,
        report.posts_cut,
        report.matches,
        report.rejected,
        len(report.users_capped),
        report.alerts_sent,
        report.forward_replies_sent,
    )
