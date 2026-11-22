from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx
import pytest
import respx
import structlog

from app.discovery.fetchers import greenhouse
from app.discovery.fetchers.errors import UNKNOWN_POSTED_AT, BoardReadError

API = "https://boards-api.greenhouse.io/v1/boards/raisin"


@respx.mock
async def test_fetch_board_name(
    client: httpx.AsyncClient, load_fixture: Callable[[str], Any]
) -> None:
    respx.get(API).mock(
        return_value=httpx.Response(200, json=load_fixture("greenhouse_board.json"))
    )

    assert await greenhouse.fetch_board_name(client, "raisin") == "Raisin"


@respx.mock
async def test_fetch_board_name_unknown_token_is_not_found(
    client: httpx.AsyncClient,
) -> None:
    respx.get("https://boards-api.greenhouse.io/v1/boards/nope").mock(
        return_value=httpx.Response(
            404, json={"status": 404, "error": "Job board not found"}
        )
    )

    with pytest.raises(BoardReadError) as exc_info:
        await greenhouse.fetch_board_name(client, "nope")

    assert exc_info.value.reason == "not_found"


@respx.mock
async def test_list_jobs_maps_fields_and_requests_no_content(
    client: httpx.AsyncClient, load_fixture: Callable[[str], Any]
) -> None:
    route = respx.get(f"{API}/jobs").mock(
        return_value=httpx.Response(200, json=load_fixture("greenhouse_jobs.json"))
    )

    jobs = await greenhouse.list_jobs(client, "raisin")

    request = route.calls.last.request
    assert "content" not in request.url.params
    assert request.headers["Accept-Encoding"] == "gzip"
    assert len(jobs) == 3
    assert jobs[0] == {
        "id": 4949391101,
        "title": "AFC Advisory Manager (f/m/d)",
        "absolute_url": "https://job-boards.eu.greenhouse.io/raisin/jobs/4949391101",
        "location": "Berlin, Berlin, Germany; Frankfurt a. M.; Hamburg; Munich",
        "first_published": "2026-08-10T09:17:19-04:00",
        "updated_at": "2026-11-06T06:01:53-05:00",
        "company_name": "Raisin",
    }


@respx.mock
async def test_list_jobs_skips_malformed_entries(client: httpx.AsyncClient) -> None:
    respx.get(f"{API}/jobs").mock(
        return_value=httpx.Response(
            200,
            json={
                "jobs": [
                    {"id": 1},
                    "junk",
                    {"id": 2, "absolute_url": "https://x.example/2"},
                ]
            },
        )
    )

    jobs = await greenhouse.list_jobs(client, "raisin")

    assert [job["id"] for job in jobs] == [2]
    assert jobs[0]["location"] is None


@respx.mock
async def test_list_jobs_skips_non_http_urls(client: httpx.AsyncClient) -> None:
    respx.get(f"{API}/jobs").mock(
        return_value=httpx.Response(
            200,
            json={
                "jobs": [
                    {"id": 1, "absolute_url": "javascript:alert(1)"},
                    {"id": 2, "absolute_url": "data:text/html,hi"},
                    {"id": 3, "absolute_url": "/jobs/3"},
                    {"id": 4, "absolute_url": "HTTPS://Job-Boards.Greenhouse.io/x/4"},
                    {"id": 5, "absolute_url": "http://x.example/5"},
                ]
            },
        )
    )

    with structlog.testing.capture_logs() as logs:
        jobs = await greenhouse.list_jobs(client, "raisin")

    assert [job["id"] for job in jobs] == [4, 5]
    rejected = [e for e in logs if e["event"] == "greenhouse_job_url_rejected"]
    assert [(e["board"], e["job_id"], e["log_level"]) for e in rejected] == [
        ("raisin", 1, "info"),
        ("raisin", 2, "info"),
        ("raisin", 3, "info"),
    ]
    assert all("javascript" not in str(e) for e in rejected)


@respx.mock
async def test_list_jobs_unexpected_shape_is_unreachable(
    client: httpx.AsyncClient,
) -> None:
    respx.get(f"{API}/jobs").mock(return_value=httpx.Response(200, json=[1, 2]))

    with pytest.raises(BoardReadError) as exc_info:
        await greenhouse.list_jobs(client, "raisin")

    assert exc_info.value.reason == "unreachable"


@pytest.mark.parametrize(
    "side_effect",
    [httpx.Response(503), httpx.Response(429), httpx.ReadTimeout("slow")],
    ids=["503", "429", "timeout"],
)
@respx.mock
async def test_list_jobs_failures_are_unreachable(
    client: httpx.AsyncClient, side_effect: httpx.Response | Exception
) -> None:
    route = respx.get(f"{API}/jobs")
    if isinstance(side_effect, httpx.Response):
        route.mock(return_value=side_effect)
    else:
        route.mock(side_effect=side_effect)

    with pytest.raises(BoardReadError) as exc_info:
        await greenhouse.list_jobs(client, "raisin")

    assert exc_info.value.reason == "unreachable"


@respx.mock
async def test_fetch_job_text_unescapes_and_strips_html(
    client: httpx.AsyncClient, load_fixture: Callable[[str], Any]
) -> None:
    respx.get(f"{API}/jobs/4949391101").mock(
        return_value=httpx.Response(200, json=load_fixture("greenhouse_job.json"))
    )

    text = await greenhouse.fetch_job_text(client, "raisin", 4949391101)

    assert text.startswith("Raisin is the world’s leading platform")
    assert "<" not in text
    assert "&lt;" not in text
    assert "&nbsp;" not in text
    assert "&amp;" not in text
    assert "the FinTech connects consumers" in text


@respx.mock
async def test_fetch_job_text_is_capped(client: httpx.AsyncClient) -> None:
    content = "&lt;p&gt;" + "x" * 30_000 + "&lt;/p&gt;"
    respx.get(f"{API}/jobs/1").mock(
        return_value=httpx.Response(200, json={"content": content})
    )

    text = await greenhouse.fetch_job_text(client, "raisin", 1)

    assert len(text) == 20_000


@respx.mock
async def test_fetch_job_text_missing_job_is_not_found(
    client: httpx.AsyncClient,
) -> None:
    respx.get(f"{API}/jobs/1").mock(return_value=httpx.Response(404))

    with pytest.raises(BoardReadError) as exc_info:
        await greenhouse.fetch_job_text(client, "raisin", 1)

    assert exc_info.value.reason == "not_found"


@pytest.mark.parametrize("token", ["../admin", "a/b", "a.b", "", "x" * 101, "acme?x=1"])
async def test_unsafe_token_is_rejected_without_request(
    client: httpx.AsyncClient, token: str
) -> None:
    with respx.mock(assert_all_called=False) as router:
        with pytest.raises(BoardReadError) as exc_info:
            await greenhouse.list_jobs(client, token)

        assert exc_info.value.reason == "not_found"
        assert not router.calls


def test_to_raw_post_maps_fixture(load_fixture: Callable[[str], Any]) -> None:
    raw_job = load_fixture("greenhouse_jobs.json")["jobs"][0]
    keys = (
        "id",
        "title",
        "absolute_url",
        "first_published",
        "updated_at",
        "company_name",
    )
    job = {key: raw_job[key] for key in keys}

    post = greenhouse.to_raw_post("raisin", job, "Some text")

    assert post.external_key == "gh:raisin/4949391101"
    assert post.url == "https://job-boards.eu.greenhouse.io/raisin/jobs/4949391101"
    assert post.job_link is not None
    assert post.title == "AFC Advisory Manager (f/m/d)"
    assert post.company == "Raisin"
    assert post.text == "Some text"
    # 2026-08-10T09:17:19-04:00 -> naive UTC
    assert post.posted_at == datetime(2026, 8, 10, 13, 17, 19)
    assert post.posted_at.tzinfo is None


def test_to_raw_post_falls_back_to_updated_at() -> None:
    job = {
        "id": 7,
        "title": "Dev",
        "absolute_url": "https://x.example/7",
        "first_published": None,
        "updated_at": "2026-11-06T06:01:53-05:00",
        "company_name": None,
    }

    post = greenhouse.to_raw_post("acme", job, "")

    assert post.posted_at == datetime(2026, 11, 6, 11, 1, 53)
    assert post.company is None


def test_to_raw_post_without_any_date_is_old() -> None:
    job = {
        "id": 8,
        "title": "Dev",
        "absolute_url": "https://x.example/8",
        "first_published": None,
        "updated_at": "not a date",
    }

    post = greenhouse.to_raw_post("acme", job, "")

    # No date means "old", never "now": an initial scan must not show it.
    assert post.posted_at == UNKNOWN_POSTED_AT
    assert greenhouse.job_posted_at(job) is None
    assert post.external_key == "gh:acme/8"


def test_to_raw_post_posted_at_override() -> None:
    job = {"id": 8, "absolute_url": "https://x.example/8"}

    post = greenhouse.to_raw_post(
        "acme", job, "", posted_at=datetime(2026, 11, 22, 12, 0)
    )

    assert post.posted_at == datetime(2026, 11, 22, 12, 0)
