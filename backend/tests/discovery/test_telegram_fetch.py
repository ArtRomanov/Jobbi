from collections.abc import AsyncIterator, Callable, Iterator
from datetime import datetime, timedelta

import httpx
import pytest
import respx

from app.discovery.fetchers.telegram import (
    MAX_RESPONSE_BYTES,
    SourceReadError,
    fetch_channel_posts,
)

CHANNEL = "jobbi_test"
BASE = f"https://t.me/s/{CHANNEL}"
NOW = datetime(2026, 11, 22, 12, 0)
CUTOFF = NOW - timedelta(days=7)


def _page(
    ids: list[int], *, age_hours: Callable[[int], float] = lambda _id: 1.0
) -> str:
    """A minimal t.me/s page; post `id` is `age_hours(id)` hours old."""
    messages = []
    for post_id in sorted(ids):
        posted = (NOW - timedelta(hours=age_hours(post_id))).isoformat() + "+00:00"
        messages.append(
            f'<div class="tgme_widget_message" data-post="{CHANNEL}/{post_id}">'
            f'<div class="tgme_widget_message_text js-message_text">Post {post_id}</div>'
            f'<a class="tgme_widget_message_date"><time datetime="{posted}"></time></a>'
            "</div>"
        )
    return f"<html><body>{''.join(messages)}</body></html>"


class Pager:
    """Serves pages of 3 posts going back from `newest`, like t.me/s does."""

    def __init__(
        self, newest: int, age_hours: Callable[[int], float] = lambda _id: 1.0
    ) -> None:
        self.newest = newest
        self.age_hours = age_hours
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        before = request.url.params.get("before")
        top = int(before) - 1 if before else self.newest
        ids = [i for i in range(top, top - 3, -1) if i > 0]
        return httpx.Response(200, text=_page(ids, age_hours=self.age_hours))


@pytest.fixture
def mock_router() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as http_client:
        yield http_client


class SleepRecorder:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


@pytest.fixture
def sleep() -> SleepRecorder:
    return SleepRecorder()


async def test_pages_back_until_known_key(
    mock_router: respx.MockRouter, client: httpx.AsyncClient, sleep: SleepRecorder
) -> None:
    pager = Pager(newest=10)
    mock_router.get(url__startswith=BASE).mock(side_effect=pager)

    posts = await fetch_channel_posts(
        client, CHANNEL, {f"tg:{CHANNEL}/5"}, CUTOFF, sleep=sleep
    )

    # The page holding the known key (7, 6, 5) is the last one; 5 itself is dropped.
    assert [p.external_key for p in posts] == [
        f"tg:{CHANNEL}/{i}" for i in (6, 7, 8, 9, 10)
    ]
    assert [r.url.params.get("before") for r in pager.requests] == [None, "8"]
    assert sleep.calls == [1.0]


async def test_stops_at_cutoff(
    mock_router: respx.MockRouter, client: httpx.AsyncClient, sleep: SleepRecorder
) -> None:
    # Post ids below 5 are older than the 7-day cutoff.
    pager = Pager(newest=10, age_hours=lambda i: 1.0 if i >= 5 else 24 * 8)
    mock_router.get(url__startswith=BASE).mock(side_effect=pager)

    posts = await fetch_channel_posts(client, CHANNEL, set(), CUTOFF, sleep=sleep)

    assert sorted(int(p.external_key.rsplit("/", 1)[1]) for p in posts) == [
        5,
        6,
        7,
        8,
        9,
        10,
    ]
    # Pages [10, 9, 8], [7, 6, 5], [4, 3, 2]: the third holds the first too-old post.
    assert len(pager.requests) == 3


async def test_stops_at_max_pages(
    mock_router: respx.MockRouter, client: httpx.AsyncClient, sleep: SleepRecorder
) -> None:
    pager = Pager(newest=100)
    mock_router.get(url__startswith=BASE).mock(side_effect=pager)

    posts = await fetch_channel_posts(
        client, CHANNEL, set(), CUTOFF, max_pages=3, sleep=sleep
    )

    assert len(pager.requests) == 3
    assert len(posts) == 9
    assert sleep.calls == [1.0, 1.0]


async def test_stops_on_empty_page(
    mock_router: respx.MockRouter, client: httpx.AsyncClient, sleep: SleepRecorder
) -> None:
    pager = Pager(newest=4)
    mock_router.get(url__startswith=BASE).mock(side_effect=pager)

    posts = await fetch_channel_posts(client, CHANNEL, set(), CUTOFF, sleep=sleep)

    # Pages: [4,3,2], [1], then an empty page ends the scan.
    assert len(posts) == 4
    assert len(pager.requests) == 3


async def test_posts_are_returned_oldest_first(
    mock_router: respx.MockRouter, client: httpx.AsyncClient, sleep: SleepRecorder
) -> None:
    pager = Pager(newest=6, age_hours=lambda i: 100 - i)
    mock_router.get(url__startswith=BASE).mock(side_effect=pager)

    posts = await fetch_channel_posts(client, CHANNEL, set(), CUTOFF, sleep=sleep)

    assert [p.posted_at for p in posts] == sorted(p.posted_at for p in posts)


async def test_request_uses_fixed_host_user_agent_and_no_redirects(
    mock_router: respx.MockRouter, client: httpx.AsyncClient, sleep: SleepRecorder
) -> None:
    route = mock_router.get(BASE).mock(return_value=httpx.Response(200, text=_page([])))

    await fetch_channel_posts(client, "Jobbi_Test", set(), CUTOFF, sleep=sleep)

    request = route.calls.last.request
    assert request.url.host == "t.me"
    assert request.url.path == f"/s/{CHANNEL}"
    assert request.headers["User-Agent"] == "Jobbi/1.0"


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (
            httpx.Response(302, headers={"Location": "https://t.me/jobbi_test"}),
            "private_or_deleted",
        ),
        (httpx.Response(404), "private_or_deleted"),
        (httpx.Response(429), "unreachable"),
        (httpx.Response(500), "unreachable"),
        (httpx.Response(503), "unreachable"),
    ],
)
async def test_http_errors_map_to_reasons(
    mock_router: respx.MockRouter,
    client: httpx.AsyncClient,
    sleep: SleepRecorder,
    response: httpx.Response,
    reason: str,
) -> None:
    mock_router.get(url__startswith=BASE).mock(return_value=response)

    with pytest.raises(SourceReadError) as exc_info:
        await fetch_channel_posts(client, CHANNEL, set(), CUTOFF, sleep=sleep)

    assert exc_info.value.reason == reason


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("boom"),
        httpx.ReadTimeout("slow"),
        httpx.RemoteProtocolError("x"),
    ],
)
async def test_network_errors_are_unreachable(
    mock_router: respx.MockRouter,
    client: httpx.AsyncClient,
    sleep: SleepRecorder,
    error: Exception,
) -> None:
    mock_router.get(url__startswith=BASE).mock(side_effect=error)

    with pytest.raises(SourceReadError) as exc_info:
        await fetch_channel_posts(client, CHANNEL, set(), CUTOFF, sleep=sleep)

    assert exc_info.value.reason == "unreachable"


async def test_error_on_second_page_raises(
    mock_router: respx.MockRouter, client: httpx.AsyncClient, sleep: SleepRecorder
) -> None:
    pager = Pager(newest=10)

    def side_effect(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("before"):
            return httpx.Response(502)
        return pager(request)

    mock_router.get(url__startswith=BASE).mock(side_effect=side_effect)

    with pytest.raises(SourceReadError):
        await fetch_channel_posts(client, CHANNEL, set(), CUTOFF, sleep=sleep)


async def test_oversized_response_is_rejected(
    mock_router: respx.MockRouter, client: httpx.AsyncClient, sleep: SleepRecorder
) -> None:
    body = b"<html>" + b"x" * (MAX_RESPONSE_BYTES + 1)
    mock_router.get(url__startswith=BASE).mock(
        return_value=httpx.Response(200, content=body)
    )

    with pytest.raises(SourceReadError) as exc_info:
        await fetch_channel_posts(client, CHANNEL, set(), CUTOFF, sleep=sleep)

    assert exc_info.value.reason == "unreachable"


async def test_invalid_channel_never_requests(
    mock_router: respx.MockRouter, client: httpx.AsyncClient, sleep: SleepRecorder
) -> None:
    route = mock_router.route()

    with pytest.raises(ValueError):
        await fetch_channel_posts(client, "../admin", set(), CUTOFF, sleep=sleep)

    assert not route.called
