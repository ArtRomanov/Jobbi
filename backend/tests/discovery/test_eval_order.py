"""Evaluation order and per-source cap (backlog #19): forwarded posts first,
then round-robin over sources, freshest first; at most PER_SOURCE_RUN_LIMIT
posts of one source per run (file-backed SQLite, fake Groq, fixed clock)."""

from datetime import datetime, timedelta

import groq
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.discovery import service
from app.discovery.service import DiscoveryConfig, evaluate_pending
from app.models.forwarded_post import ForwardedPost
from app.models.vacancy import Vacancy
from app.models.vacancy_seen_key import VacancySeenKey
from tests.discovery.test_service import (
    CONFIG,
    NOW,
    at,
    make_source,
    make_user,
    status_error,
    vacancies,
)


async def add_posts(
    db: async_sessionmaker[AsyncSession],
    user_id: str,
    source_id: str | None,
    name: str,
    hours_ago: list[int],
    *,
    forwarded: bool = False,
) -> None:
    """Pending posts "MATCH <name><hours ago>" posted `hours_ago` hours before
    NOW, all found at the same moment (one fetch)."""
    found_at = NOW - timedelta(minutes=30)
    async with db() as session:
        for hours in hours_ago:
            key = f"tg:{name}/{hours}"
            session.add(
                VacancySeenKey(
                    user_id=user_id, external_key=key, first_seen_at=found_at
                )
            )
            session.add(
                Vacancy(
                    user_id=user_id,
                    source_id=source_id,
                    external_key=key,
                    url=f"https://t.me/{name}/{hours}",
                    text=f"MATCH {name}{hours}",
                    posted_at=NOW - timedelta(hours=hours),
                    found_at=found_at,
                    state="pending",
                )
            )
            if forwarded:
                session.add(
                    ForwardedPost(
                        user_id=user_id,
                        external_key=key,
                        chat_id=1,
                        message_id=hours,
                        created_at=found_at,
                    )
                )
        await session.commit()


async def pending_texts(db: async_sessionmaker[AsyncSession]) -> set[str]:
    return {row.text for row in await vacancies(db) if row.state == "pending"}


async def _evaluate(factory, ai, sleep, moment: datetime = NOW, config=CONFIG):
    return await evaluate_pending(factory, ai, at(moment), config=config, sleep=sleep)


async def test_freshest_post_of_a_source_goes_first(factory, db, ai, sleep) -> None:
    user_id = await make_user(db)
    source = await make_source(db, user_id, handle="a")
    await add_posts(db, user_id, source, "a", [5, 1, 30, 3, 2, 4])

    await _evaluate(factory, ai, sleep)

    assert ai.posts_sent == [f"MATCH a{h}" for h in (1, 2, 3, 4, 5, 30)]


async def test_sources_take_turns(factory, db, ai, sleep) -> None:
    user_id = await make_user(db)
    a = await make_source(db, user_id, handle="a")
    b = await make_source(db, user_id, handle="b")
    c = await make_source(db, user_id, handle="c")
    await add_posts(db, user_id, a, "a", [1, 2, 3])
    await add_posts(db, user_id, b, "b", [10, 20, 30])
    await add_posts(db, user_id, c, "c", [5])

    await _evaluate(factory, ai, sleep)

    # Round 1: each source's freshest post (fresher first), then round 2...
    assert ai.calls == [
        ["MATCH a1", "MATCH c5", "MATCH b10", "MATCH a2", "MATCH b20"],
        ["MATCH a3", "MATCH b30"],
    ]


async def test_per_source_cap_defers_the_rest_to_the_next_run(
    factory, db, ai, sleep, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "PER_SOURCE_RUN_LIMIT", 3)
    user_id = await make_user(db)
    busy = await make_source(db, user_id, handle="busy")
    quiet = await make_source(db, user_id, handle="quiet")
    await add_posts(db, user_id, busy, "busy", [1, 2, 3, 4, 5, 6, 7])
    await add_posts(db, user_id, quiet, "quiet", [8])

    report = await _evaluate(factory, ai, sleep)

    # The cap holds across batches of one run (5 + 3 would allow more).
    assert ai.posts_sent == [
        "MATCH busy1",
        "MATCH quiet8",
        "MATCH busy2",
        "MATCH busy3",
    ]
    assert report.posts_deferred == 4
    assert await pending_texts(db) == {f"MATCH busy{h}" for h in (4, 5, 6, 7)}

    second = await _evaluate(factory, ai, sleep, NOW + timedelta(hours=1))

    assert ai.posts_sent[4:] == ["MATCH busy4", "MATCH busy5", "MATCH busy6"]
    assert second.posts_deferred == 1
    third = await _evaluate(factory, ai, sleep, NOW + timedelta(hours=2))
    assert ai.posts_sent[7:] == ["MATCH busy7"]
    assert third.posts_deferred == 0
    assert await pending_texts(db) == set()


async def test_daily_cap_is_still_the_overall_limit(factory, db, ai, sleep) -> None:
    user_id = await make_user(db)
    a = await make_source(db, user_id, handle="a")
    b = await make_source(db, user_id, handle="b")
    await add_posts(db, user_id, a, "a", [1, 2, 3, 4, 5])
    await add_posts(db, user_id, b, "b", [6, 7, 8, 9, 10])
    config = DiscoveryConfig(model="m", daily_limit=4)

    report = await _evaluate(factory, ai, sleep, config=config)

    assert ai.posts_sent == ["MATCH a1", "MATCH b6", "MATCH a2", "MATCH b7"]
    assert report.users_capped == {user_id}
    assert report.posts_deferred == 0  # waiting for the daily cap, not deferred
    assert len(await pending_texts(db)) == 6


async def test_forwarded_posts_go_first_and_are_never_capped(
    factory, db, ai, sleep, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "PER_SOURCE_RUN_LIMIT", 2)
    user_id = await make_user(db)
    watched = await make_source(db, user_id, handle="w")
    await add_posts(db, user_id, watched, "w", [1, 2, 3])
    # Forwarded from unwatched channels (no source) and from the watched one.
    await add_posts(db, user_id, None, "fwd", [40, 50, 60], forwarded=True)
    await add_posts(db, user_id, watched, "wf", [70], forwarded=True)

    report = await _evaluate(factory, ai, sleep)

    assert ai.posts_sent[:4] == [
        "MATCH fwd40",
        "MATCH fwd50",
        "MATCH fwd60",
        "MATCH wf70",
    ]
    # The forwarded post of the watched source does not use its cap.
    assert ai.posts_sent[4:] == ["MATCH w1", "MATCH w2"]
    assert report.posts_deferred == 1
    assert await pending_texts(db) == {"MATCH w3"}


async def test_rows_without_a_source_are_not_capped_together(
    factory, db, ai, sleep, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Posts of a removed source (source_id NULL) are not one capped group."""
    monkeypatch.setattr(service, "PER_SOURCE_RUN_LIMIT", 2)
    user_id = await make_user(db)
    await add_posts(db, user_id, None, "gone", [1, 2, 3, 4])

    report = await _evaluate(factory, ai, sleep)

    assert ai.posts_sent == [f"MATCH gone{h}" for h in (1, 2, 3, 4)]
    assert report.posts_deferred == 0


@pytest.mark.parametrize(
    ("error", "status"),
    [(groq.RateLimitError, 429), (groq.InternalServerError, 503)],
)
async def test_deferred_counted_when_the_ai_stops_the_run(
    factory, db, ai, sleep, monkeypatch: pytest.MonkeyPatch, error, status
) -> None:
    """A rate limit (stops the run) or a transport error (stops the user)
    after a source reached its cap: its waiting posts still count."""
    monkeypatch.setattr(service, "PER_SOURCE_RUN_LIMIT", 3)
    user_id = await make_user(db)
    busy = await make_source(db, user_id, handle="busy")
    quiet = await make_source(db, user_id, handle="quiet")
    await add_posts(db, user_id, busy, "busy", [1, 2, 3, 4, 5, 6, 7])
    await add_posts(db, user_id, quiet, "quiet", [8, 9, 10, 11, 12])
    create = ai.chat.completions.create

    async def fail_second_call(**kwargs):
        if ai.calls:
            ai.errors.append(status_error(error, status))
        return await create(**kwargs)

    monkeypatch.setattr(ai.chat.completions, "create", fail_second_call)

    report = await _evaluate(factory, ai, sleep)

    assert len(ai.calls) == 2  # busy reached its cap in the first batch
    assert report.posts_deferred == 4  # busy4..busy7


async def test_deferred_counted_when_the_daily_cap_ends_the_run(
    factory, db, ai, sleep, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "PER_SOURCE_RUN_LIMIT", 3)
    user_id = await make_user(db)
    busy = await make_source(db, user_id, handle="busy")
    quiet = await make_source(db, user_id, handle="quiet")
    await add_posts(db, user_id, busy, "busy", [1, 2, 3, 4, 5, 6, 7])
    await add_posts(db, user_id, quiet, "quiet", [8, 9, 10])
    config = DiscoveryConfig(model="m", daily_limit=5)

    report = await _evaluate(factory, ai, sleep, config=config)

    assert len(ai.posts_sent) == 5 and report.users_capped == {user_id}
    assert report.posts_deferred == 4  # busy4..busy7 were held by its cap
