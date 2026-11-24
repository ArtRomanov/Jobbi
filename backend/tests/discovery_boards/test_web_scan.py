"""Paging rules of `web_scan.read_listing` (respx + stub resolver, no DNS)."""

import httpx
import pytest
import respx

from app.discovery.fetchers.safe_http import PageFetchError, UnsafeUrlError
from app.discovery.fetchers.web_listing import ListingJob
from app.discovery.web_scan import read_listing

PUBLIC_IP = "93.184.216.34"
HTML = {"content-type": "text/html; charset=utf-8"}


async def _resolve(host: str, port: int) -> list[str]:
    return {"other.example.org": ["151.101.1.69"]}.get(host, [PUBLIC_IP])


async def _no_sleep(_: float) -> None:
    return None


def _page(job_ids: list[str], next_href: str | None = None) -> str:
    links = "".join(f'<a href="/vacancy/{j}"><h3>Job {j}</h3></a>' for j in job_ids)
    pager = f'<a rel="next" href="{next_href}">next</a>' if next_href else ""
    return f"<html><body>{links}{pager}</body></html>"


async def _read(url: str = "https://example.com/jobs", **kwargs: object):
    return await read_listing(
        url,
        None,
        total_timeout_s=kwargs.pop("total_timeout_s", 30.0),  # type: ignore[arg-type]
        resolver=_resolve,
        sleep=_no_sleep,
        **kwargs,  # type: ignore[arg-type]
    )


@respx.mock
async def test_follows_next_pages_and_dedupes_jobs() -> None:
    # The more specific route first: respx picks the first match.
    respx.get(f"https://{PUBLIC_IP}/jobs", params={"page": "2"}).respond(
        200, headers=HTML, text=_page(["b", "c"])
    )
    respx.get(f"https://{PUBLIC_IP}/jobs").respond(
        200, headers=HTML, text=_page(["a", "b"], "/jobs?page=2")
    )

    result = await _read()

    assert [job.url for job in result.jobs] == [
        "https://example.com/vacancy/a",
        "https://example.com/vacancy/b",
        "https://example.com/vacancy/c",
    ]
    assert result.pages_read == 2


@respx.mock
async def test_does_not_follow_next_page_on_another_host() -> None:
    route = respx.get(f"https://{PUBLIC_IP}/jobs").respond(
        200, headers=HTML, text=_page(["a"], "https://other.example.org/jobs?page=2")
    )

    result = await _read()

    assert result.pages_read == 1
    assert route.call_count == 1


@respx.mock
async def test_stops_when_a_page_brings_nothing_new() -> None:
    # A site that ignores the page parameter serves page 1 again.
    route = respx.get(f"https://{PUBLIC_IP}/jobs").mock(
        side_effect=lambda request: httpx.Response(
            200, headers=HTML, text=_page(["a"], "/jobs?page=9")
        )
    )

    result = await _read()

    assert route.call_count == 2
    assert result.pages_read == 2
    assert len(result.jobs) == 1


@respx.mock
async def test_respects_max_pages_and_stop_after() -> None:
    respx.get(f"https://{PUBLIC_IP}/jobs").mock(
        side_effect=lambda request: httpx.Response(
            200,
            headers=HTML,
            text=_page(
                [f"p{request.url.params.get('page', '1')}"],
                f"/jobs?page={int(request.url.params.get('page', '1')) + 1}",
            ),
        )
    )

    capped = await _read(max_pages=3)
    stopped = await _read(stop_after=lambda jobs: jobs[0].url.endswith("/p2"))

    assert capped.pages_read == 3
    assert stopped.pages_read == 2


@respx.mock
async def test_time_budget_keeps_pages_already_read() -> None:
    respx.get(f"https://{PUBLIC_IP}/jobs").respond(
        200, headers=HTML, text=_page(["a"], "/jobs?page=2")
    )

    # The pause before page 2 does not fit into what is left of the budget.
    result = await _read(total_timeout_s=5.0, pause_s=10.0)

    assert result.pages_read == 1
    assert len(result.jobs) == 1


@respx.mock
async def test_later_page_failure_or_unsafe_redirect_keeps_earlier_pages() -> None:
    respx.get(f"https://{PUBLIC_IP}/jobs").respond(
        200, headers=HTML, text=_page(["a"], "/jobs/2")
    )
    respx.get(f"https://{PUBLIC_IP}/jobs/2").respond(
        302, headers={"location": "http://10.0.0.1/"}
    )

    result = await _read()

    assert result.pages_read == 1


@respx.mock
async def test_first_page_errors_are_raised() -> None:
    respx.get(f"https://{PUBLIC_IP}/jobs").respond(503)

    with pytest.raises(PageFetchError):
        await _read()
    with pytest.raises(UnsafeUrlError):
        await _read("http://127.0.0.1/jobs")


@respx.mock
async def test_async_stop_after_is_awaited() -> None:
    respx.get(f"https://{PUBLIC_IP}/jobs").mock(
        side_effect=lambda request: httpx.Response(
            200,
            headers=HTML,
            text=_page(
                [f"p{request.url.params.get('page', '1')}"],
                f"/jobs?page={int(request.url.params.get('page', '1')) + 1}",
            ),
        )
    )
    seen: list[str] = []

    async def _stop(jobs: list[ListingJob]) -> bool:
        seen.append(jobs[0].url)
        return jobs[0].url.endswith("/p2")

    result = await _read(stop_after=_stop)

    assert result.pages_read == 2
    assert seen == [
        "https://example.com/vacancy/p1",
        "https://example.com/vacancy/p2",
    ]
