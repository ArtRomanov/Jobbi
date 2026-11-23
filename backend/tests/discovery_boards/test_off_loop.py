"""CPU-heavy parsing of fetched pages runs in a worker thread, not on the event loop."""

import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
import respx

from app.discovery import web_scan
from app.discovery.board_scan import fetch_board
from app.discovery.fetchers import greenhouse, lever, teamtailor
from app.discovery.fetchers.board_http import html_to_text
from tests.discovery_boards.conftest import FIXTURES

FEED_URL = "https://approvalmax.teamtailor.com/jobs.rss"
REAL_FEED = (FIXTURES / "teamtailor_approvalmax.rss").read_bytes()
PUBLIC_IP = "93.184.216.34"
HTML = {"content-type": "text/html; charset=utf-8"}


def _on_main_thread() -> bool:
    return threading.current_thread() is threading.main_thread()


def _recording(calls: list[bool], real: Callable[..., Any]) -> Callable[..., Any]:
    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        calls.append(_on_main_thread())
        return real(*args, **kwargs)

    return _wrapped


@respx.mock
async def test_board_text_conversion_runs_off_the_event_loop(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    on_main: list[bool] = []
    for module in (teamtailor, greenhouse, lever):
        monkeypatch.setattr(module, "html_to_text", _recording(on_main, html_to_text))
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=REAL_FEED))
    respx.get("https://api.lever.co/v0/postings/acme").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "1",
                    "hostedUrl": "https://jobs.lever.co/acme/1",
                    "text": "Dev",
                    "createdAt": 1_790_000_000_000,
                    "lists": [{"text": "Req", "content": "<li>Py</li>"}],
                }
            ],
        )
    )
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").mock(
        return_value=httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 7,
                        "absolute_url": "https://acme.example/jobs/7",
                        "title": "Dev",
                        "first_published": "2026-11-07T10:00:00Z",
                    }
                ]
            },
        )
    )
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs/7").mock(
        return_value=httpx.Response(200, json={"content": "&lt;p&gt;Hi&lt;/p&gt;"})
    )
    now = datetime(2026, 11, 8, 12, 0)

    for kind, handle in (
        ("teamtailor", "approvalmax"),
        ("lever", "acme"),
        ("greenhouse", "acme"),
    ):
        result = await fetch_board(
            client,
            kind,
            handle,
            set(),
            now=now,
            cutoff=now - timedelta(days=3650),
            initial=False,
        )
        assert result.posts, kind

    assert on_main  # the converter was used
    assert not any(on_main)


async def _resolve(host: str, port: int) -> list[str]:
    return [PUBLIC_IP]


async def _no_sleep(_: float) -> None:
    return None


@respx.mock
async def test_listing_is_parsed_off_the_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    on_main: list[bool] = []
    monkeypatch.setattr(
        web_scan, "parse_listing", _recording(on_main, web_scan.parse_listing)
    )
    respx.get(f"https://{PUBLIC_IP}/jobs").respond(
        200, headers=HTML, text='<a href="/vacancy/1"><h3>Job</h3></a>'
    )

    result = await web_scan.read_listing(
        "https://example.com/jobs",
        None,
        total_timeout_s=30.0,
        resolver=_resolve,
        sleep=_no_sleep,
    )

    assert len(result.jobs) == 1
    assert on_main == [False]
