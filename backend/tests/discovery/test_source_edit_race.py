"""Edits racing the worker (spec 010 Slice 6): the `revision` guard drops
results fetched under an old link/filter, and the first-scan lease
(`initial_attempt_started_at`) is set while an attempt runs.

The edit is simulated from inside the HTTP stub (respx side effect) with a
plain `sqlite3` write on the test database file: the worker holds no
transaction while it fetches, so the write goes through like a real API edit.
"""

import sqlite3
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from app.discovery.service import run_initial_scans
from tests.discovery.test_service import (
    CHANNEL_URL,
    CONFIG,
    NOW,
    Channel,
    at,
    get_source,
    make_source,
    make_user,
    seen_keys,
    vacancies,
)
from tests.discovery.test_web_service import (
    UNREACHABLE,
    WATCHING_SINCE,
    by_job,
    check,
    make_web_source,
    queue_rows,
    sites,  # noqa: F401 - fixture
    site,  # noqa: F401 - fixture
)
from tests.discovery.web_stubs import JobPage, WebSite

# --- helpers -----------------------------------------------------------------------


@pytest.fixture
def db_file(factory: Any) -> Path:
    return Path(factory.maker.kw["bind"].url.database)


def run_sql(db_file: Path, sql: str, *params: object) -> list[tuple[Any, ...]]:
    with sqlite3.connect(db_file, timeout=5) as conn:
        rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def bump_revision(db_file: Path, source_id: str) -> None:
    """What an Edit of the link/pattern does to the source row."""
    run_sql(
        db_file,
        "UPDATE vacancy_sources SET revision = revision + 1 WHERE id = ?",
        source_id,
    )


def once(action: Callable[[], None]) -> Callable[..., None]:
    done = False

    def hook(*_: object) -> None:
        nonlocal done
        if not done:
            done = True
            action()

    return hook


def lease(db_file: Path, source_id: str) -> Any:
    [(value,)] = run_sql(
        db_file,
        "SELECT initial_attempt_started_at FROM vacancy_sources WHERE id = ?",
        source_id,
    )
    return value


# --- revision guard: listing -------------------------------------------------------


async def test_edit_during_listing_fetch_stores_nothing_then_next_run_stores(
    factory, db, db_file, site: WebSite, http, ai, sleep
) -> None:
    user_id = await make_user(db)
    source_id = await make_web_source(db, user_id, site)
    site.add("a", "MATCH React role")
    site.on_request = once(lambda: bump_revision(db_file, source_id))

    report = await check(factory, http, ai, sleep)

    assert site.listing_requests == [1]
    # Loaded with revision 0, edited to 1 mid-fetch: the stale listing is
    # dropped (no rows, no seen keys) and the detail step stops too.
    assert await vacancies(db) == []
    assert await seen_keys(db) == {}
    assert site.job_requests == []
    assert report.sources_read == 0 and report.posts_stored == 0
    source = await get_source(db, source_id)
    assert source.last_checked_at == WATCHING_SINCE

    later = NOW + timedelta(hours=1)
    report = await check(factory, http, ai, sleep, later)

    [card] = await vacancies(db)
    assert card.state == "new" and card.text == "MATCH React role"
    assert set(await seen_keys(db)) == {site.key(source_id, "a")}
    source = await get_source(db, source_id)
    assert source.revision == 1 and source.last_checked_at == later


async def test_edit_during_failed_listing_does_not_record_the_failure(
    factory, db, db_file, site: WebSite, http, ai, sleep
) -> None:
    user_id = await make_user(db)
    source_id = await make_web_source(db, user_id, site)
    site.add("a")
    site.failing_pages.add(1)
    site.on_request = once(lambda: bump_revision(db_file, source_id))

    report = await check(factory, http, ai, sleep)

    assert report.sources_failed == 1
    source = await get_source(db, source_id)
    # The failure was about the old link: the edited source stays clean.
    assert (source.failing_since, source.last_error) == (None, None)

    await check(factory, http, ai, sleep, NOW + timedelta(hours=1))

    source = await get_source(db, source_id)
    assert source.last_error == UNREACHABLE


async def test_edit_during_telegram_check_stores_nothing(
    factory, db, db_file, respx_mock: respx.MockRouter, http, ai, sleep
) -> None:
    from app.discovery.service import check_all

    user_id = await make_user(db)
    source_id = await make_source(db, user_id, scanned=True)
    stub = Channel(on_request=once(lambda: bump_revision(db_file, source_id)))
    stub.add(10, "MATCH")
    respx_mock.get(CHANNEL_URL).mock(side_effect=stub)

    await check_all(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

    assert stub.requests >= 1
    assert await vacancies(db) == []
    assert await seen_keys(db) == {}


# --- revision guard: detail step ---------------------------------------------------


async def test_detail_step_stops_when_the_source_is_edited(
    factory, db, db_file, site: WebSite, http, ai, sleep
) -> None:
    user_id = await make_user(db)
    source_id = await make_web_source(db, user_id, site)
    site.listed.append("listed")
    site.failing_pages.add(1)  # listing fails: only the detail step runs
    await queue_rows(db, user_id, source_id, site, ["a", "b", "c"])
    for job_id in ("a", "b", "c"):
        site.pages[job_id] = _page(f"MATCH {job_id}")
    site.on_request = once_matching(lambda: bump_revision(db_file, source_id))

    await check(factory, http, ai, sleep)

    # Page `a` was fetched, then its write saw the new revision: nothing
    # written, and `b`/`c` were not read.
    assert site.job_requests == ["a"]
    rows = by_job(await vacancies(db))
    assert sorted(rows) == ["a", "b", "c"]
    assert all(
        row.needs_detail and row.text == "" and row.detail_attempts == 0
        for row in rows.values()
    )
    assert ai.calls == []


@pytest.mark.parametrize("status", [404, 500])
async def test_detail_step_drops_nothing_after_an_edit(
    factory, db, db_file, site: WebSite, http, ai, sleep, status: int
) -> None:
    """Gone (404) and failing (500) pages write nothing after an edit either."""
    user_id = await make_user(db)
    source_id = await make_web_source(db, user_id, site)
    site.listed.append("listed")
    site.failing_pages.add(1)
    await queue_rows(db, user_id, source_id, site, ["a", "b"])
    site.pages["a"] = _page("gone", status=status)
    site.pages["b"] = _page("MATCH b")
    site.on_request = once_matching(lambda: bump_revision(db_file, source_id))

    await check(factory, http, ai, sleep)

    assert site.job_requests == ["a"]
    rows = by_job(await vacancies(db))
    assert sorted(rows) == ["a", "b"]
    assert rows["a"].detail_attempts == 0


# --- first-scan lease --------------------------------------------------------------


async def test_lease_is_set_during_the_attempt_and_cleared_after_success(
    factory, db, db_file, respx_mock: respx.MockRouter, http, ai, sleep
) -> None:
    user_id = await make_user(db, description=None)
    source_id = await make_source(db, user_id)
    seen: list[Any] = []
    stub = Channel(on_request=lambda: seen.append(lease(db_file, source_id)))
    stub.add(10, "MATCH")
    respx_mock.get(CHANNEL_URL).mock(side_effect=stub)

    await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

    assert seen and all(str(value).startswith("2026-11-22 12:00:00") for value in seen)
    source = await get_source(db, source_id)
    assert source.initial_attempt_started_at is None
    assert source.initial_scan_completed_at == NOW
    assert len(await vacancies(db)) == 1


async def test_lease_is_cleared_after_a_failed_attempt(
    factory, db, db_file, respx_mock: respx.MockRouter, http, ai, sleep
) -> None:
    user_id = await make_user(db, description=None)
    source_id = await make_source(db, user_id)
    seen: list[Any] = []

    def fail(request: httpx.Request) -> httpx.Response:
        seen.append(lease(db_file, source_id))
        return httpx.Response(500)

    respx_mock.get(CHANNEL_URL).mock(side_effect=fail)

    await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

    assert seen and all(value is not None for value in seen)
    source = await get_source(db, source_id)
    assert source.initial_attempt_started_at is None
    assert source.initial_scan_completed_at is None
    assert source.last_error is not None


async def test_lease_is_cleared_when_the_fetch_raises(
    factory, db, respx_mock: respx.MockRouter, http, ai, sleep
) -> None:
    user_id = await make_user(db, description=None)
    source_id = await make_source(db, user_id)

    def boom(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("unexpected")

    respx_mock.get(CHANNEL_URL).mock(side_effect=boom)

    with pytest.raises(RuntimeError):
        await run_initial_scans(
            factory, http, ai, at(NOW), config=CONFIG, sleep=sleep
        )

    source = await get_source(db, source_id)
    assert source.initial_attempt_started_at is None


async def test_source_deleted_during_the_attempt_does_not_crash(
    factory, db, db_file, respx_mock: respx.MockRouter, http, ai, sleep
) -> None:
    user_id = await make_user(db, description=None)
    source_id = await make_source(db, user_id)
    second_id = await make_source(db, user_id, handle="second_channel")
    stub = Channel(
        on_request=once(
            lambda: run_sql(
                db_file, "DELETE FROM vacancy_sources WHERE id = ?", source_id
            )
        )
    )
    stub.add(10, "MATCH")
    respx_mock.get(CHANNEL_URL).mock(side_effect=stub)
    second = Channel(name="second_channel")
    second.add(20, "MATCH second")
    respx_mock.get("https://t.me/s/second_channel").mock(side_effect=second)

    report = await run_initial_scans(
        factory, http, ai, at(NOW), config=CONFIG, sleep=sleep
    )

    assert report.sources_read == 1
    [card] = await vacancies(db)
    assert card.source_id == second_id
    assert run_sql(db_file, "SELECT id FROM vacancy_sources") == [(second_id,)]
    assert (await get_source(db, second_id)).initial_attempt_started_at is None


async def test_source_edited_before_its_attempt_is_skipped(
    factory, db, db_file, respx_mock: respx.MockRouter, http, ai, sleep, monkeypatch
) -> None:
    """Loaded, then edited before the attempt starts: no lease, no fetch."""
    from app.discovery import service

    user_id = await make_user(db, description=None)
    source_id = await make_source(db, user_id)
    stub = Channel()
    stub.add(10, "MATCH")
    respx_mock.get(CHANNEL_URL).mock(side_effect=stub)
    original = service._load_sources

    async def load_then_edit(*args: Any, **kwargs: Any) -> Any:
        sources = await original(*args, **kwargs)
        bump_revision(db_file, source_id)
        return sources

    monkeypatch.setattr(service, "_load_sources", load_then_edit)

    await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

    assert stub.requests == 0
    assert lease(db_file, source_id) is None


# --- small stubs -------------------------------------------------------------------


def _page(text: str, **kwargs: Any) -> JobPage:
    return JobPage(text=text, **kwargs)


def once_matching(action: Callable[[], None]) -> Callable[[httpx.Request], None]:
    """Run `action` on the first job-page request only (the listing is let by)."""
    done = False

    def hook(request: httpx.Request) -> None:
        nonlocal done
        if not done and "/vacancy/" in request.url.path:
            done = True
            action()

    return hook
