"""Read a Greenhouse or Lever board and split its unseen jobs for storage.

Network only: no database access here (the caller loads the known keys before
and stores the result after, each in its own short session).

Initial scan (the source was just added): every listed job that is not yet
known is recorded as seen, so jobs that were already open never come back as
"new"; only jobs published inside the lookback window become posts (pending
cards). A job without a usable date counts as old.

Hourly check: every listed job that is not yet known becomes a post. A job
without a date gets the check time as its `posted_at`.
"""

import asyncio
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypeAlias

import httpx

from app.discovery.fetchers import greenhouse, lever
from app.discovery.fetchers.errors import BoardReadError
from app.discovery.types import RawPost

__all__ = ["BOARD_KINDS", "BoardFetch", "board_key_prefix", "fetch_board"]

BOARD_KINDS = frozenset({"greenhouse", "lever", "lever_eu"})

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
    """Prefix shared by the seen keys of one board (`gh:acme/`, `lever:acme/`)."""
    if kind == "greenhouse":
        return f"gh:{handle}/"
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
            `unreachable`). A Greenhouse job that 404s between the listing
            and its detail request (closed meanwhile) is skipped instead.
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
            if exc.reason == "not_found":
                # Closed between the listing and now; not recorded, so it is
                # picked up again if it reappears.
                continue
            raise
        result.posts.append(
            greenhouse.to_raw_post(token, job, text, posted_at=posted_at or now)
        )
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
    result = BoardFetch()
    handled: set[str] = set()
    for posting in await lever.list_postings(client, kind, company):
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
