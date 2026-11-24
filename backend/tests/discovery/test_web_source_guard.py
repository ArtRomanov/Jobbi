"""Web sources record what is listed when they are saved: no worker run ever
gives them a first scan. A web row that somehow lacks a completed first scan
is left alone by both entry points; a watched one is read by `check_all`."""

import respx

from app.discovery.service import check_all, run_initial_scans
from tests.discovery.test_service import (
    CONFIG,
    NOW,
    at,
    get_source,
    make_user,
    seen_keys,
    vacancies,
)
from tests.discovery.test_web_service import WATCHING_SINCE, make_web_source
from tests.discovery.web_stubs import Sites, WebSite, resolve


async def test_web_sources_never_get_a_first_scan(
    factory, db, http, ai, sleep, respx_mock: respx.MockRouter
) -> None:
    sites = Sites(respx_mock)
    watched = sites.add(WebSite(name="watched"))
    unscanned = sites.add(WebSite(name="unscanned"))
    for site in (watched, unscanned):
        site.add("a", "Plain job")
    user_id = await make_user(db, description=None)
    watched_id = await make_web_source(db, user_id, watched)
    unscanned_id = await make_web_source(db, user_id, unscanned, scanned=False)

    await run_initial_scans(factory, http, ai, at(NOW), config=CONFIG, sleep=sleep)

    assert not respx_mock.calls

    await check_all(
        factory, http, ai, at(NOW), config=CONFIG, sleep=sleep, web_resolver=resolve
    )

    assert watched.listing_requests == [1]
    assert unscanned.requests == []
    source = await get_source(db, unscanned_id)
    assert source.last_checked_at == WATCHING_SINCE
    assert source.failing_since is None and source.last_error is None
    assert (await get_source(db, watched_id)).last_checked_at == NOW
    assert list(await seen_keys(db)) == [watched.key(watched_id, "a")]
    assert len(await vacancies(db)) == 1
