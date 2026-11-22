from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx
import pytest
import respx

from app.discovery.fetchers import lever
from app.discovery.fetchers.errors import UNKNOWN_POSTED_AT, BoardReadError

US_ACME = "https://api.lever.co/v0/postings/acme"


def _postings(count: int, start: int = 0) -> list[dict[str, Any]]:
    return [
        {
            "id": f"id-{i}",
            "hostedUrl": f"https://jobs.lever.co/acme/id-{i}",
            "text": f"Job {i}",
        }
        for i in range(start, start + count)
    ]


def _paged(total: int) -> Callable[[httpx.Request], httpx.Response]:
    """Fake Lever endpoint serving ``total`` postings with skip/limit."""

    def handler(request: httpx.Request) -> httpx.Response:
        skip = int(request.url.params["skip"])
        limit = int(request.url.params["limit"])
        return httpx.Response(
            200, json=_postings(max(0, min(limit, total - skip)), skip)
        )

    return handler


@respx.mock
async def test_list_postings_pages_until_short_page(client: httpx.AsyncClient) -> None:
    route = respx.get(US_ACME).mock(side_effect=_paged(110))

    postings = await lever.list_postings(client, "lever", "acme")

    assert len(postings) == 110
    params = [call.request.url.params for call in route.calls]
    assert [p["skip"] for p in params] == ["0", "50", "100"]
    assert all(p["limit"] == "50" and p["mode"] == "json" for p in params)


@respx.mock
async def test_list_postings_exact_multiple_ends_on_empty_page(
    client: httpx.AsyncClient,
) -> None:
    route = respx.get(US_ACME).mock(side_effect=_paged(100))

    postings = await lever.list_postings(client, "lever", "acme")

    assert len(postings) == 100
    assert route.call_count == 3


@respx.mock
async def test_list_postings_stops_at_page_limit(client: httpx.AsyncClient) -> None:
    route = respx.get(US_ACME).mock(side_effect=_paged(10_000))

    postings = await lever.list_postings(client, "lever", "acme", page_size=2)

    assert route.call_count == lever.MAX_PAGES
    assert len(postings) == 2 * lever.MAX_PAGES


@pytest.mark.parametrize(
    ("kind", "host"),
    [("lever", "https://api.lever.co"), ("lever_eu", "https://api.eu.lever.co")],
)
@respx.mock
async def test_region_host_from_kind(
    client: httpx.AsyncClient, kind: str, host: str
) -> None:
    route = respx.get(f"{host}/v0/postings/acme").mock(
        return_value=httpx.Response(200, json=[])
    )

    assert await lever.list_postings(client, kind, "acme") == []
    assert route.called


def test_unknown_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="Not a Lever source kind"):
        lever.api_host("greenhouse")


@respx.mock
async def test_eu_404_is_not_found_and_other_region_is_not_tried(
    client: httpx.AsyncClient,
) -> None:
    eu = respx.get("https://api.eu.lever.co/v0/postings/acme").mock(
        return_value=httpx.Response(
            404, json={"ok": False, "error": "Document not found"}
        )
    )
    us = respx.get(US_ACME)

    with pytest.raises(BoardReadError) as exc_info:
        await lever.list_postings(client, "lever_eu", "acme")

    assert exc_info.value.reason == "not_found"
    assert eu.called
    assert not us.called


@pytest.mark.parametrize(
    "side_effect",
    [httpx.Response(503), httpx.Response(429), httpx.ReadTimeout("slow")],
    ids=["503", "429", "timeout"],
)
@respx.mock
async def test_failures_are_unreachable(
    client: httpx.AsyncClient, side_effect: httpx.Response | Exception
) -> None:
    route = respx.get(US_ACME)
    if isinstance(side_effect, httpx.Response):
        route.mock(return_value=side_effect)
    else:
        route.mock(side_effect=side_effect)

    with pytest.raises(BoardReadError) as exc_info:
        await lever.list_postings(client, "lever", "acme")

    assert exc_info.value.reason == "unreachable"


@respx.mock
async def test_failure_on_later_page_is_unreachable(client: httpx.AsyncClient) -> None:
    respx.get(US_ACME).mock(
        side_effect=[httpx.Response(200, json=_postings(50)), httpx.Response(503)]
    )

    with pytest.raises(BoardReadError) as exc_info:
        await lever.list_postings(client, "lever", "acme")

    assert exc_info.value.reason == "unreachable"


@respx.mock
async def test_non_list_response_is_unreachable(client: httpx.AsyncClient) -> None:
    respx.get(US_ACME).mock(return_value=httpx.Response(200, json={"ok": True}))

    with pytest.raises(BoardReadError) as exc_info:
        await lever.list_postings(client, "lever", "acme")

    assert exc_info.value.reason == "unreachable"


@respx.mock
async def test_list_postings_drops_items_without_id_or_url(
    client: httpx.AsyncClient,
) -> None:
    respx.get(US_ACME).mock(
        return_value=httpx.Response(
            200, json=[{"id": "a"}, {"hostedUrl": "https://x"}, "junk", *_postings(1)]
        )
    )

    postings = await lever.list_postings(client, "lever", "acme")

    assert [p["id"] for p in postings] == ["id-0"]


@pytest.mark.parametrize("company", ["../admin", "a/b", "a.b", ""])
async def test_unsafe_company_is_rejected_without_request(
    client: httpx.AsyncClient, company: str
) -> None:
    with respx.mock(assert_all_called=False) as router:
        with pytest.raises(BoardReadError) as exc_info:
            await lever.list_postings(client, "lever", company)

        assert exc_info.value.reason == "not_found"
        assert not router.calls


@pytest.mark.parametrize(
    ("slug", "expected"),
    [
        ("acme-labs", "Acme Labs"),
        ("acme", "Acme"),
        ("acme_labs", "Acme Labs"),
        ("acme--labs-", "Acme Labs"),
        ("ACME-labs", "Acme Labs"),
        ("42-ventures", "42 Ventures"),
    ],
)
def test_display_name_from_slug(slug: str, expected: str) -> None:
    assert lever.display_name_from_slug(slug) == expected


def test_to_raw_post_maps_binance_fixture(load_fixture: Callable[[str], Any]) -> None:
    posting = load_fixture("lever_binance.json")[0]

    post = lever.to_raw_post("lever", "binance", posting)

    assert post.external_key == "lever:binance/7c5d03b5-ce74-45b7-b38d-c46adce58047"
    assert (
        post.url == "https://jobs.lever.co/binance/7c5d03b5-ce74-45b7-b38d-c46adce58047"
    )
    assert post.job_link is not None
    assert post.title == "Business Compliance Manager - Payments"
    assert post.company == "Binance"
    assert post.text.startswith("Binance is a leading global blockchain ecosystem")
    assert "\nResponsibilities\n" in post.text
    assert "\nRequirements\n" in post.text
    assert "<" not in post.text
    assert post.posted_at == datetime(2026, 8, 4, 6, 17, 5, 174000)
    assert post.posted_at.tzinfo is None


def test_to_raw_post_maps_eu_fixture(load_fixture: Callable[[str], Any]) -> None:
    posting = load_fixture("lever_eu_lever.json")[0]

    post = lever.to_raw_post("lever_eu", "lever", posting)

    assert post.external_key == "lever_eu:lever/065f4538-7347-4207-909f-4ea68f63b4af"
    assert post.url.startswith("https://jobs.eu.lever.co/lever/")
    assert post.title == "API Engineer"
    assert post.company == "Lever"
    assert "THE SKILL SET" in post.text
    assert post.posted_at == datetime(2020, 6, 24, 21, 58, 59, 222000)


def test_to_raw_post_caps_text_and_handles_missing_created_at() -> None:
    posting = {
        "id": "x",
        "hostedUrl": "https://jobs.lever.co/acme/x",
        "text": "Dev",
        "descriptionPlain": "y" * 30_000,
    }

    post = lever.to_raw_post("lever", "acme", posting)

    assert len(post.text) == 20_000
    # No date means "old", never "now": an initial scan must not show it.
    assert post.posted_at == UNKNOWN_POSTED_AT
    assert lever.posting_posted_at(posting) is None


def test_to_raw_post_posted_at_override() -> None:
    posting = {"id": "x", "hostedUrl": "https://jobs.lever.co/acme/x"}

    post = lever.to_raw_post(
        "lever", "acme", posting, posted_at=datetime(2026, 11, 22, 12, 0)
    )

    assert post.posted_at == datetime(2026, 11, 22, 12, 0)


@pytest.mark.parametrize("value", ["1700000000000", True, None, 10**20])
def test_posting_posted_at_rejects_bad_values(value: Any) -> None:
    assert lever.posting_posted_at({"createdAt": value}) is None


@respx.mock
async def test_check_company_makes_one_small_request(
    client: httpx.AsyncClient,
) -> None:
    route = respx.get(US_ACME).mock(return_value=httpx.Response(200, json=[]))

    await lever.check_company(client, "lever", "acme")

    assert route.call_count == 1
    params = route.calls.last.request.url.params
    assert (params["mode"], params["limit"]) == ("json", "1")


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(404), "not_found"),
        (httpx.Response(500), "unreachable"),
        (httpx.Response(200, json={"error": "x"}), "unreachable"),
    ],
)
@respx.mock
async def test_check_company_failures(
    client: httpx.AsyncClient, response: httpx.Response, reason: str
) -> None:
    respx.get(US_ACME).mock(return_value=response)

    with pytest.raises(BoardReadError) as exc_info:
        await lever.check_company(client, "lever", "acme")

    assert exc_info.value.reason == reason
