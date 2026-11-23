"""safe_http follow-up (spec 010 §2.6): bot-challenge detection and ``fetch_json``."""

import time
from collections.abc import AsyncGenerator

import httpx
import pytest
import respx

from app.discovery.fetchers import safe_http
from app.discovery.fetchers.safe_http import (
    USER_AGENT,
    FetchedJson,
    PageFetchError,
    UnsafeUrlError,
    fetch_html,
    fetch_json,
    make_client,
)
from tests.discovery_boards.test_safe_http import PUBLIC, PUBLIC_IP

HTML = {"content-type": "text/html; charset=utf-8"}
JSON = {"content-type": "application/json; charset=utf-8"}
URL = "https://jobs.example.com/"

CF_CHALLENGE_PAGE = (
    "<!DOCTYPE html><html><head><title>Just a moment...</title></head>"
    '<body><script src="/cdn-cgi/challenge-platform/h/b/orchestrate/x"></script>'
    "</body></html>"
)


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with make_client() as http_client:
        yield http_client


async def _reason_html(client: httpx.AsyncClient, url: str = URL) -> str:
    with pytest.raises(PageFetchError) as exc_info:
        await fetch_html(url, client=client, resolver=PUBLIC)
    return exc_info.value.reason


async def _reason_json(client: httpx.AsyncClient, url: str = URL) -> str:
    with pytest.raises(PageFetchError) as exc_info:
        await fetch_json(url, client=client, resolver=PUBLIC)
    return exc_info.value.reason


# --- bot-protection challenges --------------------------------------------------------


@pytest.mark.parametrize("status", [403, 429, 503])
@respx.mock
async def test_cf_mitigated_challenge_is_blocked(
    status: int, client: httpx.AsyncClient
) -> None:
    # The live careers.manychat.com/positions answer: 403 + `cf-mitigated`.
    respx.get(f"https://{PUBLIC_IP}/").respond(
        status,
        headers={**HTML, "cf-mitigated": "Challenge", "server": "cloudflare"},
        text=CF_CHALLENGE_PAGE,
    )

    assert await _reason_html(client) == "blocked"


@pytest.mark.parametrize("status", [403, 503])
@respx.mock
async def test_cloudflare_challenge_page_without_header_is_blocked(
    status: int, client: httpx.AsyncClient
) -> None:
    respx.get(f"https://{PUBLIC_IP}/").respond(
        status, headers={**HTML, "server": "cloudflare"}, text=CF_CHALLENGE_PAGE
    )

    assert await _reason_html(client) == "blocked"


@pytest.mark.parametrize(
    ("status", "headers", "text"),
    [
        (403, {**HTML, "server": "cloudflare"}, "<html>Forbidden</html>"),
        (403, {**HTML, "server": "nginx"}, CF_CHALLENGE_PAGE),
        (403, {**HTML, "cf-mitigated": "block"}, "x"),
        (500, {**HTML, "server": "cloudflare"}, CF_CHALLENGE_PAGE),
        (500, {**HTML, "cf-mitigated": "challenge"}, "x"),
        (404, {**HTML, "cf-mitigated": "challenge"}, "x"),
    ],
    ids=[
        "plain-cf-403",
        "markup-without-cf",
        "other-mitigation",
        "cf-500-markup",
        "cf-500-header",
        "404-header",
    ],
)
@respx.mock
async def test_other_error_pages_keep_their_reason(
    status: int, headers: dict[str, str], text: str, client: httpx.AsyncClient
) -> None:
    respx.get(f"https://{PUBLIC_IP}/").respond(status, headers=headers, text=text)

    expected = "not_found" if status == 404 else "unreachable"
    assert await _reason_html(client) == expected


@respx.mock
async def test_challenge_check_reads_only_the_page_top(
    client: httpx.AsyncClient,
) -> None:
    padding = "x" * (safe_http.CHALLENGE_SNIFF_BYTES + 10)
    respx.get(f"https://{PUBLIC_IP}/").respond(
        403,
        headers={**HTML, "server": "cloudflare"},
        text=f"<html>{padding}{CF_CHALLENGE_PAGE}",
    )

    assert await _reason_html(client) == "unreachable"


@respx.mock
async def test_blocked_on_a_redirect_target(client: httpx.AsyncClient) -> None:
    respx.get(f"https://{PUBLIC_IP}/a").respond(302, headers={"location": "/b"})
    respx.get(f"https://{PUBLIC_IP}/b").respond(
        403, headers={"cf-mitigated": "challenge"}, text=""
    )

    assert await _reason_html(client, "https://jobs.example.com/a") == "blocked"


@respx.mock
async def test_challenge_cookie_is_not_kept(client: httpx.AsyncClient) -> None:
    respx.get(f"https://{PUBLIC_IP}/").respond(
        403,
        headers={"cf-mitigated": "challenge", "set-cookie": "__cf_bm=x; Path=/"},
        text="",
    )

    assert await _reason_html(client) == "blocked"
    assert not client.cookies


# --- fetch_json -----------------------------------------------------------------------


@respx.mock
async def test_fetch_json_returns_parsed_data_under_the_same_guard(
    client: httpx.AsyncClient,
) -> None:
    route = respx.get(f"https://{PUBLIC_IP}/api?page=1").respond(
        200, headers=JSON, json={"data": [1, 2]}
    )

    result = await fetch_json(
        "https://jobs.example.com/api?page=1", client=client, resolver=PUBLIC
    )

    assert result == FetchedJson(
        final_url="https://jobs.example.com/api?page=1",
        status=200,
        data={"data": [1, 2]},
    )
    request = route.calls.last.request
    assert request.headers["host"] == "jobs.example.com"
    assert request.headers["accept"] == "application/json"
    assert request.headers["accept-encoding"] == "identity"
    assert request.headers["user-agent"] == USER_AGENT
    assert "cookie" not in request.headers


@pytest.mark.parametrize(
    "content_type", ["text/html", "text/plain", "application/xml", ""]
)
@respx.mock
async def test_fetch_json_rejects_other_content_types(
    content_type: str, client: httpx.AsyncClient
) -> None:
    headers = {"content-type": content_type} if content_type else {}
    respx.get(f"https://{PUBLIC_IP}/").respond(200, headers=headers, content=b"{}")

    assert await _reason_json(client) == "not_json"


@pytest.mark.parametrize(
    "body",
    [b"{not json", b"", b"\xff\xfe\x00", b"[" * 100_000 + b"]" * 100_000],
    ids=["broken", "empty", "bad-bytes", "deep-nesting"],
)
@respx.mock
async def test_fetch_json_invalid_body_is_not_json(
    body: bytes, client: httpx.AsyncClient
) -> None:
    respx.get(f"https://{PUBLIC_IP}/").respond(200, headers=JSON, content=body)

    assert await _reason_json(client) == "not_json"


@respx.mock
async def test_fetch_json_keeps_the_redirect_and_address_rules(
    client: httpx.AsyncClient,
) -> None:
    respx.get(f"https://{PUBLIC_IP}/r").respond(
        302, headers={"location": "http://127.0.0.1/admin"}
    )

    with pytest.raises(UnsafeUrlError):
        await fetch_json("https://jobs.example.com/r", client=client, resolver=PUBLIC)
    with pytest.raises(UnsafeUrlError):
        await fetch_json("http://10.0.0.1/x", client=client, resolver=PUBLIC)
    with pytest.raises(UnsafeUrlError):
        await fetch_json(
            "https://jobs.example.com:8080/", client=client, resolver=PUBLIC
        )


@respx.mock
async def test_fetch_json_size_cap(client: httpx.AsyncClient) -> None:
    respx.get(f"https://{PUBLIC_IP}/").respond(200, headers=JSON, content=b"1" * 2_000)

    with pytest.raises(PageFetchError) as exc_info:
        await fetch_json(URL, client=client, resolver=PUBLIC, max_bytes=1_000)
    assert exc_info.value.reason == "too_large"


@pytest.mark.parametrize(
    ("status", "reason"), [(404, "not_found"), (500, "unreachable")]
)
@respx.mock
async def test_fetch_json_error_statuses(
    status: int, reason: str, client: httpx.AsyncClient
) -> None:
    respx.get(f"https://{PUBLIC_IP}/").respond(status, headers=JSON, json={})

    assert await _reason_json(client) == reason


@respx.mock
async def test_fetch_json_blocked_challenge(client: httpx.AsyncClient) -> None:
    respx.get(f"https://{PUBLIC_IP}/").respond(
        403, headers={"cf-mitigated": "challenge"}, text=""
    )

    assert await _reason_json(client) == "blocked"


async def test_fetch_json_refuses_a_misconfigured_client() -> None:
    async with httpx.AsyncClient(follow_redirects=True) as bad:
        with pytest.raises(ValueError):
            await fetch_json(URL, client=bad)


@respx.mock
async def test_fetch_json_parsing_counts_toward_the_total_time(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    respx.get(f"https://{PUBLIC_IP}/").respond(200, headers=JSON, json={"a": 1})

    def slow_parse(body: bytes) -> object:
        time.sleep(1.0)
        return {}

    monkeypatch.setattr(safe_http, "_parse_json", slow_parse)
    started = time.monotonic()

    with pytest.raises(PageFetchError) as exc_info:
        await fetch_json(URL, client=client, resolver=PUBLIC, timeout_s=0.3)

    assert exc_info.value.reason == "unreachable"
    assert time.monotonic() - started < 0.9


@respx.mock
async def test_fetch_html_still_rejects_json(client: httpx.AsyncClient) -> None:
    respx.get(f"https://{PUBLIC_IP}/").respond(200, headers=JSON, json={})

    assert await _reason_html(client) == "not_html"
