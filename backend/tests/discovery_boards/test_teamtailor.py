"""Teamtailor RSS fetcher: real ApprovalMax feed, hostile XML, board_scan wiring."""

from datetime import datetime, timedelta

import httpx
import pytest
import respx

from app.discovery.board_scan import BOARD_KINDS, board_key_prefix, fetch_board
from app.discovery.fetchers import teamtailor
from app.discovery.fetchers.board_http import MAX_RESPONSE_BYTES, MAX_TEXT_CHARS
from app.discovery.fetchers.errors import UNKNOWN_POSTED_AT, BoardReadError
from tests.discovery_boards.conftest import FIXTURES

FEED_URL = "https://approvalmax.teamtailor.com/jobs.rss"
REAL_FEED = (FIXTURES / "teamtailor_approvalmax.rss").read_bytes()


def _rss(items: str, *, title: str = "Acme", prolog: str = "") -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"{prolog}<rss version='2.0'><channel><title>{title}</title>"
        f"{items}</channel></rss>"
    ).encode()


def _item(
    link: str,
    *,
    title: str = "Dev",
    pub: str = "Mon, 02 Nov 2026 17:47:02 +0000",
    description: str = "&lt;p&gt;Hello&lt;/p&gt;",
) -> str:
    return (
        f"<item><title>{title}</title><link>{link}</link>"
        f"<pubDate>{pub}</pubDate><description>{description}</description></item>"
    )


# --- Real feed --------------------------------------------------------------------


@respx.mock
async def test_real_feed_maps_channel_and_items(client: httpx.AsyncClient) -> None:
    route = respx.get(FEED_URL).mock(
        return_value=httpx.Response(200, content=REAL_FEED)
    )

    feed = await teamtailor.fetch_feed(client, "approvalmax")

    request = route.calls.last.request
    assert request.headers["User-Agent"] == "Jobbi/1.0"
    assert feed.company == "ApprovalMax"
    assert [item.job_id for item in feed.items] == [
        "8683780",
        "8653872",
        "8648921",
        "8607219",
        "7535472",
        "7219058",
    ]
    first = feed.items[0]
    assert first.title == "Director of Product"
    assert (
        first.link
        == "https://approvalmax.teamtailor.com/jobs/8683780-director-of-product"
    )
    assert first.posted_at == datetime(2026, 11, 6, 15, 13, 50)
    # +0100 offset converted to naive UTC.
    assert feed.items[3].posted_at == datetime(2026, 10, 23, 8, 52, 3)


@respx.mock
async def test_real_feed_to_raw_post(client: httpx.AsyncClient) -> None:
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=REAL_FEED))
    feed = await teamtailor.fetch_feed(client, "approvalmax")

    post = teamtailor.to_raw_post("approvalmax", feed.company, feed.items[0])

    assert post.external_key == "tt:approvalmax/8683780"
    assert post.url == post.job_link
    assert post.job_link == (
        "https://approvalmax.teamtailor.com/jobs/8683780-director-of-product"
    )
    assert post.title == "Director of Product"
    assert post.company == "ApprovalMax"
    assert post.posted_at == datetime(2026, 11, 6, 15, 13, 50)
    assert post.text.startswith("About ApprovalMax:\nApprovalMax is a B2B SaaS")
    assert "<" not in post.text and "&lt;" not in post.text
    assert len(post.text) <= MAX_TEXT_CHARS


@respx.mock
async def test_fetch_board_name_is_channel_title(client: httpx.AsyncClient) -> None:
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=REAL_FEED))

    assert await teamtailor.fetch_board_name(client, "approvalmax") == "ApprovalMax"


@respx.mock
async def test_board_scan_initial_keeps_only_recent_items(
    client: httpx.AsyncClient,
) -> None:
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=REAL_FEED))
    now = datetime(2026, 11, 8, 12, 0)

    result = await fetch_board(
        client,
        "teamtailor",
        "approvalmax",
        {"tt:approvalmax/8653872"},
        now=now,
        cutoff=now - timedelta(days=7),
        initial=True,
    )

    # Known key skipped; posts sorted oldest first.
    assert [p.external_key for p in result.posts] == [
        "tt:approvalmax/8648921",
        "tt:approvalmax/8683780",
    ]
    assert result.seen_only_keys == [
        "tt:approvalmax/8607219",
        "tt:approvalmax/7535472",
        "tt:approvalmax/7219058",
    ]


def test_board_scan_knows_teamtailor() -> None:
    assert "teamtailor" in BOARD_KINDS
    assert board_key_prefix("teamtailor", "approvalmax") == "tt:approvalmax/"


# --- Item filtering -----------------------------------------------------------


def test_items_without_a_numeric_job_id_are_skipped() -> None:
    body = _rss(
        _item("https://acme.teamtailor.com/jobs")
        + _item("https://acme.teamtailor.com/jobs/abc-dev")
        + _item("javascript:alert(1)//jobs/1-x")
        + _item("/jobs/2-relative")
        + _item("https://acme.teamtailor.com/jobs/3-dev/apply/x")
        + _item("https://acme.teamtailor.com/jobs/4-dev")
        + _item("https://careers.acme.com/jobs/5")
        + _item("https://acme.teamtailor.com/jobs/4-dev")  # duplicate
    )

    feed = teamtailor.parse_feed("acme", body)

    assert [item.job_id for item in feed.items] == ["4", "5"]


def test_undated_or_bad_date_item() -> None:
    body = _rss(_item("https://acme.teamtailor.com/jobs/1-a", pub="not a date"))

    [item] = teamtailor.parse_feed("acme", body).items

    assert item.posted_at is None
    post = teamtailor.to_raw_post("acme", "Acme", item)
    assert post.posted_at == UNKNOWN_POSTED_AT


def test_oversized_link_is_skipped() -> None:
    link = "https://acme.teamtailor.com/jobs/1-" + "a" * 3000
    assert teamtailor.parse_feed("acme", _rss(_item(link))).items == []


# --- Hostile / broken responses -----------------------------------------------

BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
 <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
 <!ENTITY lol5 "&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;">
 <!ENTITY lol6 "&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;">
 <!ENTITY lol7 "&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;">
 <!ENTITY lol8 "&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;">
 <!ENTITY lol9 "&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;">
]>
<rss version="2.0"><channel><title>&lol9;</title>
<item><title>&lol9;</title><link>https://acme.teamtailor.com/jobs/1-a</link>
<description>&lol9;</description></item></channel></rss>"""

EXTERNAL_ENTITY = b"""<?xml version="1.0"?>
<!DOCTYPE rss [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<rss version="2.0"><channel><title>&xxe;</title></channel></rss>"""

EXTERNAL_DTD = b"""<?xml version="1.0"?>
<!DOCTYPE rss SYSTEM "http://169.254.169.254/evil.dtd">
<rss version="2.0"><channel><title>Acme</title></channel></rss>"""


@pytest.mark.parametrize(
    "body",
    [
        BILLION_LAUGHS,
        EXTERNAL_ENTITY,
        EXTERNAL_DTD,
        b"<rss><channel><title>Acme</title>",  # truncated
        b"not xml at all",
        b"",
        b"<html><body>Teamtailor</body></html>",
        b"<rss version='2.0'><title>no channel</title></rss>",
        b'{"jobs": []}',
    ],
    ids=[
        "billion-laughs",
        "external-entity",
        "external-dtd",
        "truncated",
        "not-xml",
        "empty",
        "html",
        "no-channel",
        "json",
    ],
)
def test_hostile_or_malformed_xml_is_unreachable(body: bytes) -> None:
    with pytest.raises(BoardReadError) as exc_info:
        teamtailor.parse_feed("acme", body)

    assert exc_info.value.reason == "unreachable"


@respx.mock
async def test_entity_bomb_over_http_is_unreachable(client: httpx.AsyncClient) -> None:
    respx.get("https://acme.teamtailor.com/jobs.rss").mock(
        return_value=httpx.Response(200, content=BILLION_LAUGHS)
    )

    with pytest.raises(BoardReadError) as exc_info:
        await teamtailor.fetch_feed(client, "acme")

    assert exc_info.value.reason == "unreachable"


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(404), "not_found"),
        (httpx.Response(500), "unreachable"),
        (httpx.Response(429), "unreachable"),
        (
            httpx.Response(302, headers={"Location": "http://169.254.169.254/"}),
            "unreachable",
        ),
        (httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1)), "unreachable"),
        (httpx.ConnectError("boom"), "unreachable"),
        (httpx.ReadTimeout("slow"), "unreachable"),
    ],
    ids=["404", "500", "429", "redirect", "too-big", "connect-error", "timeout"],
)
@respx.mock
async def test_http_failures(
    client: httpx.AsyncClient, response: httpx.Response | Exception, reason: str
) -> None:
    route = respx.get("https://acme.teamtailor.com/jobs.rss").mock(
        side_effect=[response]
    )

    with pytest.raises(BoardReadError) as exc_info:
        await teamtailor.fetch_feed(client, "acme")

    assert exc_info.value.reason == reason
    assert route.call_count == 1  # redirects are not followed


def test_untitled_channel_has_no_company() -> None:
    feed = teamtailor.parse_feed("acme", _rss("", title=""))
    assert feed.company is None


@respx.mock
async def test_untitled_channel_board_name_is_unreachable(
    client: httpx.AsyncClient,
) -> None:
    respx.get("https://acme.teamtailor.com/jobs.rss").mock(
        return_value=httpx.Response(200, content=_rss("", title=""))
    )

    with pytest.raises(BoardReadError):
        await teamtailor.fetch_board_name(client, "acme")


@pytest.mark.parametrize(
    "handle",
    ["", "-acme", "acme-", "a.b", "acme/../x", "evil.com#", "Acme", "a" * 64, "аcme"],
)
async def test_invalid_handle_makes_no_request(
    client: httpx.AsyncClient, handle: str
) -> None:
    with respx.mock(assert_all_called=False) as router:
        with pytest.raises(BoardReadError) as exc_info:
            await teamtailor.fetch_feed(client, handle)
        assert not router.calls

    assert exc_info.value.reason == "not_found"
