"""Ashby job-board fetcher: real ManyChat answer, hostile JSON, board_scan wiring."""

import json
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
import respx

from app.discovery.board_scan import BOARD_KINDS, board_key_prefix, fetch_board
from app.discovery.fetchers import ashby
from app.discovery.fetchers.board_http import MAX_RESPONSE_BYTES, MAX_TEXT_CHARS
from app.discovery.fetchers.errors import UNKNOWN_POSTED_AT, BoardReadError
from tests.discovery_boards.conftest import FIXTURES

API_URL = "https://api.ashbyhq.com/posting-api/job-board/manychat"
REAL = json.loads((FIXTURES / "ashby_manychat.json").read_text(encoding="utf-8"))
FIRST_ID = "72eaca21-1d04-4e08-ac70-c987519dda1f"


def _job(job_id: str = "j1", **overrides: Any) -> dict[str, Any]:
    job: dict[str, Any] = {
        "id": job_id,
        "title": "Dev",
        "jobUrl": f"https://jobs.ashbyhq.com/acme/{job_id}",
        "publishedAt": "2026-11-02T17:47:02.000+00:00",
        "descriptionPlain": "Hello",
        "descriptionHtml": "<p>Hello</p>",
        "isListed": True,
    }
    job.update(overrides)
    return job


def _board(*jobs: dict[str, Any]) -> dict[str, Any]:
    return {"jobs": list(jobs), "apiVersion": "1"}


# --- Real board -------------------------------------------------------------------


@respx.mock
async def test_real_board_lists_jobs_from_the_fixed_api_url(
    client: httpx.AsyncClient,
) -> None:
    route = respx.get(API_URL).mock(return_value=httpx.Response(200, json=REAL))

    jobs = await ashby.list_jobs(client, "manychat")

    request = route.calls.last.request
    assert request.url.params["includeCompensation"] == "false"
    assert request.headers["User-Agent"] == "Jobbi/1.0"
    assert request.headers["Accept"] == "application/json"
    assert [job["id"] for job in jobs] == [job["id"] for job in REAL["jobs"]]


@respx.mock
async def test_real_job_to_raw_post(client: httpx.AsyncClient) -> None:
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=REAL))
    [first, *_] = await ashby.list_jobs(client, "manychat")

    post = ashby.to_raw_post("manychat", first)

    assert post.external_key == f"ashby:manychat/{FIRST_ID}"
    assert post.url == f"https://jobs.ashbyhq.com/manychat/{FIRST_ID}"
    assert post.job_link == post.url
    assert post.title == "Staff Platform Product Manager, Core"
    assert post.company == "Manychat"
    # publishedAt "2026-11-18T12:21:01.571+00:00" as naive UTC.
    assert post.posted_at == datetime(2026, 11, 18, 12, 21, 1, 571000)
    assert post.text.startswith("WHO WE ARE")
    assert len(post.text) <= MAX_TEXT_CHARS


def test_display_name_is_the_title_cased_slug() -> None:
    assert ashby.display_name("manychat") == "Manychat"
    assert ashby.display_name("acme-labs") == "Acme Labs"
    assert ashby.display_name("kraken.com") == "Kraken.com"


@respx.mock
async def test_check_board_reads_the_listing(client: httpx.AsyncClient) -> None:
    route = respx.get(API_URL).mock(return_value=httpx.Response(200, json=_board()))

    await ashby.check_board(client, "manychat")  # an empty board is still a board

    assert route.call_count == 1


@respx.mock
async def test_board_scan_initial_keeps_only_recent_jobs(
    client: httpx.AsyncClient,
) -> None:
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=REAL))
    now = datetime(2026, 11, 21, 12, 0)
    known = f"ashby:manychat/{REAL['jobs'][3]['id']}"

    result = await fetch_board(
        client,
        "ashby",
        "manychat",
        {known},
        now=now,
        cutoff=now - timedelta(days=7),
        initial=True,
    )

    assert [p.external_key for p in result.posts] == [f"ashby:manychat/{FIRST_ID}"]
    assert result.seen_only_keys == [
        f"ashby:manychat/{REAL['jobs'][1]['id']}",
        f"ashby:manychat/{REAL['jobs'][2]['id']}",
    ]


@respx.mock
async def test_board_scan_hourly_posts_every_unseen_job_oldest_first(
    client: httpx.AsyncClient,
) -> None:
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=REAL))
    now = datetime(2026, 11, 21, 12, 0)

    result = await fetch_board(
        client,
        "ashby",
        "manychat",
        set(),
        now=now,
        cutoff=now - timedelta(days=7),
        initial=False,
    )

    dates = [p.posted_at for p in result.posts]
    assert len(dates) == 4 and dates == sorted(dates)
    assert result.seen_only_keys == []


def test_board_scan_knows_ashby() -> None:
    assert "ashby" in BOARD_KINDS
    assert board_key_prefix("ashby", "manychat") == "ashby:manychat/"


# --- Mapping details --------------------------------------------------------------


def test_html_description_is_used_when_plain_is_missing() -> None:
    job = _job(
        descriptionPlain=None, descriptionHtml="<p>Line one</p><ul><li>Py</li></ul>"
    )

    assert ashby.to_raw_post("acme", job).text == "Line one\nPy"


def test_job_without_any_description_has_empty_text() -> None:
    job = _job(descriptionPlain="", descriptionHtml=None)

    assert ashby.to_raw_post("acme", job).text == ""


def test_long_description_is_capped() -> None:
    job = _job(descriptionPlain="x" * (MAX_TEXT_CHARS + 50))

    assert len(ashby.to_raw_post("acme", job).text) == MAX_TEXT_CHARS


@pytest.mark.parametrize(
    "value",
    [None, "", "not a date", 1_790_000_000, "2026-13-40T00:00:00Z", ["x"]],
)
def test_bad_or_missing_date(value: Any) -> None:
    job = _job(publishedAt=value)

    assert ashby.job_posted_at(job) is None
    assert ashby.to_raw_post("acme", job).posted_at == UNKNOWN_POSTED_AT


def test_naive_date_is_taken_as_utc() -> None:
    assert ashby.job_posted_at(_job(publishedAt="2026-11-02T17:47:02")) == datetime(
        2026, 11, 2, 17, 47, 2
    )


def test_offset_date_is_converted_to_utc() -> None:
    job = _job(publishedAt="2026-11-02T17:47:02+02:00")

    assert ashby.job_posted_at(job) == datetime(2026, 11, 2, 15, 47, 2)


def test_job_key() -> None:
    assert ashby.job_key("acme", "j1") == "ashby:acme/j1"


# --- Item filtering ---------------------------------------------------------------


def test_unusable_jobs_are_dropped() -> None:
    jobs = [
        _job("ok-1"),
        "not a dict",
        _job("no-url", jobUrl=None),
        _job("js", jobUrl="javascript:alert(1)"),
        _job("relative", jobUrl="/acme/relative"),
        _job("unlisted", isListed=False),
        _job("bad id/../x"),
        _job("x" * 65),
        {"title": "no id", "jobUrl": "https://jobs.ashbyhq.com/acme/1"},
        _job(123),  # type: ignore[arg-type]
        _job("long-url", jobUrl="https://jobs.ashbyhq.com/" + "a" * 3000),
        _job("ok-1"),  # duplicate
        _job("ok-2", isListed=None),  # unknown listing flag: kept
    ]

    usable = ashby.parse_board("acme", {"jobs": jobs})

    assert [job["id"] for job in usable] == ["ok-1", "ok-2"]


def test_job_count_is_capped() -> None:
    jobs = [_job(f"j{i}") for i in range(ashby.MAX_JOBS + 10)]

    assert len(ashby.parse_board("acme", {"jobs": jobs})) == ashby.MAX_JOBS


@pytest.mark.parametrize(
    "data",
    [[], "jobs", None, 42, {"jobs": None}, {"jobs": "x"}, {"jobs": {}}, {}],
    ids=["list", "str", "null", "int", "jobs-null", "jobs-str", "jobs-dict", "empty"],
)
def test_wrong_shape_is_unreachable(data: Any) -> None:
    with pytest.raises(BoardReadError) as exc_info:
        ashby.parse_board("acme", data)

    assert exc_info.value.reason == "unreachable"


# --- HTTP failures ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(404, text="Not Found"), "not_found"),
        (httpx.Response(500), "unreachable"),
        (httpx.Response(429), "unreachable"),
        (
            httpx.Response(302, headers={"Location": "http://169.254.169.254/"}),
            "unreachable",
        ),
        (httpx.Response(200, content=b"<html>no</html>"), "unreachable"),
        (
            httpx.Response(200, content=b"x" * (ashby.MAX_RESPONSE_BYTES + 1)),
            "unreachable",
        ),
        (
            httpx.Response(200, content=b"[" * 100_000 + b"]" * 100_000),
            "unreachable",
        ),
        (httpx.ConnectError("boom"), "unreachable"),
        (httpx.ReadTimeout("slow"), "unreachable"),
    ],
    ids=[
        "404",
        "500",
        "429",
        "redirect",
        "not-json",
        "too-big",
        "deep-nesting",
        "connect",
        "timeout",
    ],
)
@respx.mock
async def test_http_failures(
    client: httpx.AsyncClient, response: httpx.Response | Exception, reason: str
) -> None:
    route = respx.get(API_URL).mock(side_effect=[response])

    with pytest.raises(BoardReadError) as exc_info:
        await ashby.list_jobs(client, "manychat")

    assert exc_info.value.reason == reason
    assert route.call_count == 1  # redirects are not followed


def test_ashby_cap_is_its_own_and_larger_than_the_board_cap() -> None:
    # openai's board measured 14.3 MB on 2026-11-23; other boards keep 5 MB.
    assert ashby.MAX_RESPONSE_BYTES == 32 * 1024 * 1024
    assert MAX_RESPONSE_BYTES == 5 * 1024 * 1024


@respx.mock
async def test_board_between_5_and_32_mb_is_read(client: httpx.AsyncClient) -> None:
    padding = "x" * (MAX_RESPONSE_BYTES + 1024)
    body = json.dumps(_board(_job("big", descriptionPlain=padding))).encode()
    assert MAX_RESPONSE_BYTES < len(body) < ashby.MAX_RESPONSE_BYTES
    respx.get("https://api.ashbyhq.com/posting-api/job-board/acme").respond(
        200, content=body
    )

    jobs = await ashby.list_jobs(client, "acme")

    assert [job["id"] for job in jobs] == ["big"]


@respx.mock
async def test_board_json_is_parsed_off_the_event_loop(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    threads: list[bool] = []
    real = ashby.parse_json_body

    def _recording(body: bytes) -> Any:
        threads.append(threading.current_thread() is threading.main_thread())
        return real(body)

    monkeypatch.setattr(ashby, "parse_json_body", _recording)
    respx.get(API_URL).respond(200, json=REAL)

    await ashby.list_jobs(client, "manychat")

    assert threads == [False]


@pytest.mark.parametrize(
    "handle",
    [
        "",
        "-acme",
        "acme-",
        ".acme",
        "a..b",
        "acme/../x",
        "evil.com#",
        "Acme",
        "a" * 65,
        "аcme",
    ],
)
async def test_invalid_handle_makes_no_request(
    client: httpx.AsyncClient, handle: str
) -> None:
    with respx.mock(assert_all_called=False) as router:
        with pytest.raises(BoardReadError) as exc_info:
            await ashby.list_jobs(client, handle)
        assert not router.calls

    assert exc_info.value.reason == "not_found"
