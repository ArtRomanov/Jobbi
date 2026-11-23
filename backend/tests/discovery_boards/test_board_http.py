import gzip
import sys

import httpx
import pytest
import respx

from app.discovery.fetchers import board_http
from app.discovery.fetchers.board_http import get_json, html_to_text
from app.discovery.fetchers.errors import BoardReadError

URL = "https://boards-api.greenhouse.io/v1/boards/acme"


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(404, json={"status": 404}), "not_found"),
        (httpx.Response(503), "unreachable"),
        (httpx.Response(429), "unreachable"),
        (httpx.Response(500), "unreachable"),
        (
            httpx.Response(301, headers={"Location": "https://evil.example/"}),
            "unreachable",
        ),
        (httpx.Response(200, content=b"<html>not json"), "unreachable"),
    ],
    ids=["404", "503", "429", "500", "redirect-not-followed", "invalid-json"],
)
@respx.mock
async def test_status_mapping(
    client: httpx.AsyncClient, response: httpx.Response, reason: str
) -> None:
    respx.get(URL).mock(return_value=response)

    with pytest.raises(BoardReadError) as exc_info:
        await get_json(client, URL)

    assert exc_info.value.reason == reason


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ReadTimeout("slow"),
        httpx.ConnectError("down"),
        httpx.ConnectTimeout("slow"),
    ],
    ids=["read-timeout", "connect-error", "connect-timeout"],
)
@respx.mock
async def test_transport_errors_are_unreachable(
    client: httpx.AsyncClient, exc: httpx.HTTPError
) -> None:
    respx.get(URL).mock(side_effect=exc)

    with pytest.raises(BoardReadError) as exc_info:
        await get_json(client, URL)

    assert exc_info.value.reason == "unreachable"


@respx.mock
async def test_sends_user_agent_and_timeout(client: httpx.AsyncClient) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json={"ok": True}))

    assert await get_json(client, URL) == {"ok": True}

    request = route.calls.last.request
    assert request.headers["User-Agent"] == "Jobbi/1.0"
    assert request.extensions["timeout"]["read"] == 15.0


@respx.mock
async def test_body_over_cap_is_unreachable(client: httpx.AsyncClient) -> None:
    body = b'"' + b"a" * board_http.MAX_RESPONSE_BYTES + b'"'
    respx.get(URL).mock(return_value=httpx.Response(200, content=body))

    with pytest.raises(BoardReadError) as exc_info:
        await get_json(client, URL)

    assert exc_info.value.reason == "unreachable"


@respx.mock
async def test_cap_applies_to_decompressed_body(client: httpx.AsyncClient) -> None:
    raw = b'"' + b"a" * (board_http.MAX_RESPONSE_BYTES + 10) + b'"'
    compressed = gzip.compress(raw)
    assert len(compressed) < board_http.MAX_RESPONSE_BYTES
    respx.get(URL).mock(
        return_value=httpx.Response(
            200, content=compressed, headers={"Content-Encoding": "gzip"}
        )
    )

    with pytest.raises(BoardReadError) as exc_info:
        await get_json(client, URL)

    assert exc_info.value.reason == "unreachable"


@respx.mock
async def test_gzip_body_under_cap_is_decoded(client: httpx.AsyncClient) -> None:
    respx.get(URL).mock(
        return_value=httpx.Response(
            200,
            content=gzip.compress(b'{"name": "Acme"}'),
            headers={"Content-Encoding": "gzip"},
        )
    )

    assert await get_json(client, URL) == {"name": "Acme"}


@pytest.mark.parametrize(
    "body",
    [b"[" * 100_000 + b"]" * 100_000, b"\xff\xfe\x00", b"{bad"],
    ids=["deep-nesting", "bad-bytes", "broken"],
)
@respx.mock
async def test_unparsable_json_is_unreachable(
    client: httpx.AsyncClient, body: bytes
) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, content=body))

    with pytest.raises(BoardReadError) as exc_info:
        await get_json(client, URL)

    assert exc_info.value.reason == "unreachable"


@respx.mock
async def test_get_bytes_takes_its_own_cap(client: httpx.AsyncClient) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, content=b"a" * 2_000))

    assert len(await board_http.get_bytes(client, URL, max_bytes=2_000)) == 2_000
    with pytest.raises(BoardReadError):
        await board_http.get_bytes(client, URL, max_bytes=1_999)


def test_html_to_text_keeps_blocks_and_drops_tags() -> None:
    markup = (
        "<div><h2>About</h2><p>We&nbsp;build <strong>things</strong>.</p>"
        "<ul><li>Remote</li><li>EU</li></ul></div>"
    )

    text = html_to_text(markup)
    lines = text.splitlines()

    assert "<" not in text
    assert lines[0] == "About"
    assert "We build things." in lines
    assert "Remote" in lines
    assert "EU" in lines


def test_html_to_text_without_bs4(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        sys.modules, "bs4", None
    )  # makes `import bs4` raise ImportError

    text = html_to_text(
        "<p>We <b>ship</b> &amp; test</p><ul><li>One</li><li>Two</li></ul>"
    )

    assert text.splitlines() == ["We ship & test", "One", "Two"]


def _timed_text(markup: str) -> tuple[str, float]:
    import time

    started = time.perf_counter()
    text = html_to_text(markup)
    return text, time.perf_counter() - started


def test_html_to_text_many_flat_blocks_is_linear() -> None:
    text, seconds = _timed_text("<p>row</p>" * 30_000)

    assert seconds < 1.5
    assert text.splitlines()[:2] == ["row", "row"]


def test_html_to_text_deep_nesting_is_fast() -> None:
    _, seconds = _timed_text("<div>" * 5_000 + "deep" + "</div>" * 5_000)

    assert seconds < 1.5


def test_html_to_text_two_megabytes_flat_is_fast() -> None:
    _, seconds = _timed_text("<p>a</p>" * (2_000_000 // 8))

    assert seconds < 5.0


@pytest.mark.parametrize(
    "markup",
    ["", "   ", "plain text", "<<<>>>", "\x00<p>\ud800x</p>", "<br><br/>a<br>b"],
)
def test_html_to_text_odd_input(markup: str) -> None:
    assert isinstance(html_to_text(markup), str)


def test_html_to_text_br_and_inline() -> None:
    assert html_to_text("a<br>b <em>c</em><div>d</div>e").splitlines() == [
        "a",
        "b c",
        "d",
        "e",
    ]
