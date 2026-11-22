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
