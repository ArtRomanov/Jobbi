"""Read a Greenhouse, Lever or Teamtailor board and split its unseen jobs for storage.

Network only: no database access here (the caller loads the known keys before
and stores the result after, each in its own short session).

Initial scan (the source was just added): every listed job that is not yet
known is recorded as seen, so jobs that were already open never come back as
"new"; only jobs published inside the lookback window become posts (pending
cards). A job without a usable date counts as old.

Hourly check: every listed job that is not yet known becomes a post. A job
without a date gets the check time as its `posted_at`.

Greenhouse job details: only the `/jobs` listing decides whether the board is
readable. A failed detail request skips that one job without recording it (so
the next run retries it) and the other jobs go on. If more than half of a
run's detail requests fail (not counting 404 = job closed), the board is
treated as unreachable for this run, so an outage does not store a random
subset of its jobs.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeAlias

import httpx

from app.discovery.fetchers import greenhouse, lever, teamtailor
from app.discovery.fetchers.errors import BoardReadError
from app.discovery.types import RawPost

__all__ = ["BOARD_KINDS", "BoardFetch", "board_key_prefix", "fetch_board"]

logger = logging.getLogger(__name__)

BOARD_KINDS = frozenset({"greenhouse", "lever", "lever_eu", "teamtailor"})
# More than this share of failed job-detail requests in one run = outage.
MAX_DETAIL_FAILURE_SHARE = 0.5

SleepFn: TypeAlias = Callable[[float], Awaitable[None]]


@dataclass(slots=True, kw_only=True)
class BoardFetch:
    """Unseen jobs of one board read.

    `posts` become pending cards (oldest first); `seen_only_keys` are only
    recorded as seen (initial scan: published before the window or undated).
    """

    posts: list[RawPost] = field(default_factory=list)
    seen_only_keys: list[str] = field(default_factory=list)


def board_key_prefix(kind: str, handle: str) -> str:
    """Prefix shared by the seen keys of one board (`gh:acme/`, `tt:acme/`)."""
    if kind == "greenhouse":
        return f"gh:{handle}/"
    if kind == "teamtailor":
        return f"tt:{handle}/"
    if kind in ("lever", "lever_eu"):
        return f"{kind}:{handle}/"
    raise ValueError(f"Not a board kind: {kind!r}")


def _is_old(posted_at: datetime | None, cutoff: datetime) -> bool:
    return posted_at is None or posted_at < cutoff


async def fetch_board(
    client: httpx.AsyncClient,
    kind: str,
    handle: str,
    known_keys: Collection[str],
    *,
    now: datetime,
    cutoff: datetime,
    initial: bool,
    sleep: SleepFn = asyncio.sleep,
) -> BoardFetch:
    """List the board's jobs and return the unseen ones (see module docstring).

    Requests are sequential (one at a time per host). Greenhouse descriptions
    are fetched one job at a time, `greenhouse.JOB_DETAIL_PAUSE_S` apart, and
    only for jobs that will become posts.

    Raises:
        BoardReadError: the board could not be read (`not_found` /
            `unreachable`): the listing failed, or more than half of the
            Greenhouse detail requests failed. A single failed detail request
            only skips that job.
        ValueError: `kind` is not a board kind.
    """
    if kind == "greenhouse":
        result = await _fetch_greenhouse(
            client,
            handle,
            known_keys,
            now=now,
            cutoff=cutoff,
            initial=initial,
            sleep=sleep,
        )
    elif kind in ("lever", "lever_eu"):
        result = await _fetch_lever(
            client, kind, handle, known_keys, now=now, cutoff=cutoff, initial=initial
        )
    elif kind == "teamtailor":
        result = await _fetch_teamtailor(
            client, handle, known_keys, now=now, cutoff=cutoff, initial=initial
        )
    else:
        raise ValueError(f"Not a board kind: {kind!r}")
    result.posts.sort(key=lambda post: (post.posted_at, post.external_key))
    return result


async def _fetch_greenhouse(
    client: httpx.AsyncClient,
    token: str,
    known_keys: Collection[str],
    *,
    now: datetime,
    cutoff: datetime,
    initial: bool,
    sleep: SleepFn,
) -> BoardFetch:
    result = BoardFetch()
    handled: set[str] = set()
    detail_requests = 0
    detail_failures = 0
    for job in await greenhouse.list_jobs(client, token):
        key = greenhouse.job_key(token, job)
        if key in known_keys or key in handled:
            continue
        handled.add(key)
        posted_at = greenhouse.job_posted_at(job)
        if initial and _is_old(posted_at, cutoff):
            result.seen_only_keys.append(key)
            continue
        if detail_requests:
            await sleep(greenhouse.JOB_DETAIL_PAUSE_S)
        detail_requests += 1
        try:
            text = await greenhouse.fetch_job_text(client, token, job["id"])
        except BoardReadError as exc:
            # Not recorded as seen either way, so a later run retries it.
            if exc.reason == "not_found":
                logger.info("Greenhouse job %s closed before its detail", key)
            else:
                detail_failures += 1
                logger.warning("Greenhouse job %s detail failed: %s", key, exc)
            continue
        result.posts.append(
            greenhouse.to_raw_post(token, job, text, posted_at=posted_at or now)
        )
    if detail_failures > detail_requests * MAX_DETAIL_FAILURE_SHARE:
        logger.warning(
            "Greenhouse board %s: %d of %d job details failed; board unreachable",
            token,
            detail_failures,
            detail_requests,
        )
        raise BoardReadError("unreachable")
    return result


async def _fetch_lever(
    client: httpx.AsyncClient,
    kind: str,
    company: str,
    known_keys: Collection[str],
    *,
    now: datetime,
    cutoff: datetime,
    initial: bool,
) -> BoardFetch:
    postings = await lever.list_postings(client, kind, company)
    # Mapping converts description HTML to text (CPU work on remote input):
    # run it in a worker thread, off the event loop.
    return await asyncio.to_thread(
        _lever_posts,
        kind,
        company,
        postings,
        known_keys,
        now=now,
        cutoff=cutoff,
        initial=initial,
    )


def _lever_posts(
    kind: str,
    company: str,
    postings: list[dict[str, Any]],
    known_keys: Collection[str],
    *,
    now: datetime,
    cutoff: datetime,
    initial: bool,
) -> BoardFetch:
    result = BoardFetch()
    handled: set[str] = set()
    for posting in postings:
        key = lever.posting_key(kind, company, posting)
        if key in known_keys or key in handled:
            continue
        handled.add(key)
        posted_at = lever.posting_posted_at(posting)
        if initial and _is_old(posted_at, cutoff):
            result.seen_only_keys.append(key)
            continue
        result.posts.append(
            lever.to_raw_post(kind, company, posting, posted_at=posted_at or now)
        )
    return result


async def _fetch_teamtailor(
    client: httpx.AsyncClient,
    subdomain: str,
    known_keys: Collection[str],
    *,
    now: datetime,
    cutoff: datetime,
    initial: bool,
) -> BoardFetch:
    feed = await teamtailor.fetch_feed(client, subdomain)
    # Item descriptions are HTML -> text (CPU work): off the event loop.
    return await asyncio.to_thread(
        _teamtailor_posts,
        subdomain,
        feed,
        known_keys,
        now=now,
        cutoff=cutoff,
        initial=initial,
    )


def _teamtailor_posts(
    subdomain: str,
    feed: teamtailor.TeamtailorFeed,
    known_keys: Collection[str],
    *,
    now: datetime,
    cutoff: datetime,
    initial: bool,
) -> BoardFetch:
    result = BoardFetch()
    for item in feed.items:  # already deduplicated by job id
        key = teamtailor.item_key(subdomain, item.job_id)
        if key in known_keys:
            continue
        if initial and _is_old(item.posted_at, cutoff):
            result.seen_only_keys.append(key)
            continue
        result.posts.append(
            teamtailor.to_raw_post(
                subdomain, feed.company, item, posted_at=item.posted_at or now
            )
        )
    return result
