"""Tests for the listing page parser (saved real pages + small synthetic ones)."""

from pathlib import Path

import pytest

from app.discovery.fetchers.web_listing import (
    MAX_TITLE_CHARS,
    ListingJob,
    ListingPage,
    parse_listing,
)

WEB_FIXTURES = Path(__file__).parent / "fixtures" / "web"


def _parse(name: str, page_url: str, pattern: str | None = None) -> ListingPage:
    html = (WEB_FIXTURES / f"{name}.html").read_text(encoding="utf-8")
    return parse_listing(html, page_url, pattern)


def _urls(page: ListingPage) -> list[str]:
    return [job.url for job in page.jobs]


# --- saved real pages -------------------------------------------------------


def test_geekjob_vacancy_ids_with_card_titles_and_path_pagination() -> None:
    page = _parse("geekjob", "https://geekjob.ru/vacancies")

    assert len(page.jobs) == 20
    assert all("/vacancy/" in url for url in _urls(page))
    assert page.jobs[0] == ListingJob(
        url="https://geekjob.ru/vacancy/6b0412760e9260dd7d039713",
        title="Product Design Lead в Core Product",
    )
    assert page.next_url == "https://geekjob.ru/vacancies/2"


def test_geekjob_second_page_points_to_third() -> None:
    page = _parse("geekjob", "https://geekjob.ru/vacancies/2")

    assert page.next_url == "https://geekjob.ru/vacancies/3"
    assert not any("/vacancies/" in url for url in _urls(page))


def test_ingamejob_job_slugs_and_next_page_query() -> None:
    page = _parse("ingamejob", "https://ingamejob.com/en/jobs")

    assert len(page.jobs) >= 25
    assert all("/en/job/" in url for url in _urls(page))
    assert (
        ListingJob(
            url="https://ingamejob.com/en/job/ai-engineer-ai-pipelines-automation",
            title="AI Engineer (AI pipelines & automation)",
        )
        in page.jobs
    )
    assert page.next_url == "https://ingamejob.com/en/jobs?page=2"


def test_hirify_heading_inside_card_link_is_the_title() -> None:
    page = _parse("hirify", "https://hirify.me/")

    assert len(page.jobs) >= 15
    assert all("/jobs/" in url for url in _urls(page))
    assert page.jobs[0] == ListingJob(
        url="https://hirify.me/jobs/1464497-llm-agentic-ai-engineer-insurance",
        title="LLM & Agentic Consulting Engineer – Insurance Sector (AI)",
    )
    # Category pages (/ai-jobs, ...) have no segment after the job word.
    assert "https://hirify.me/ai-jobs" not in _urls(page)


def test_careerspace_job_ids() -> None:
    page = _parse("careerspace", "https://careerspace.app/jobs")

    assert len(page.jobs) == 8
    assert (
        ListingJob(
            url="https://careerspace.app/job/271944",
            title="Менеджер по работе с клиентами (B2B сегмент)",
        )
        in page.jobs
    )


@pytest.mark.parametrize("pattern", [None, "/vacancy/", "/VACANCY/"])
def test_ostrovok_vacancies_without_team_pages(pattern: str | None) -> None:
    page = _parse("ostrovok", "https://career.ostrovok.ru/vacancy", pattern)

    assert _urls(page) == [
        "https://career.ostrovok.ru/vacancy/3490",
        "https://career.ostrovok.ru/vacancy/3486",
        "https://career.ostrovok.ru/vacancy/3481",
        "https://career.ostrovok.ru/vacancy/3463",
    ]
    assert page.jobs[0].title == "Senior Data Engineer"
    assert not any("/teams/" in url for url in _urls(page))


def test_yandex_vacancies_found_and_navigation_skipped() -> None:
    page = _parse("yandex", "https://yandex.ru/jobs/locations/yerevan")

    urls = _urls(page)
    assert "https://yandex.ru/jobs/vacancies/produktoviy-analitik-49741" in urls
    # Header / footer links (?from=cp_header / cp_footer) are site chrome.
    assert not any("cp_header" in url or "cp_footer" in url for url in urls)
    # /jobs/vacancies (filters) has nothing after the last job-like segment.
    assert not any(url.startswith("https://yandex.ru/jobs/vacancies?") for url in urls)


def test_yandex_with_pattern_keeps_only_vacancy_links() -> None:
    page = _parse(
        "yandex", "https://yandex.ru/jobs/locations/yerevan", "/jobs/vacancies/"
    )

    assert len(page.jobs) >= 15
    assert all("/jobs/vacancies/" in url for url in _urls(page))
    assert (
        ListingJob(
            url="https://yandex.ru/jobs/vacancies/produktoviy-analitik-49741",
            title="Продуктовый аналитик",
        )
        in page.jobs
    )


def test_hirehi_filter_widget_links_are_not_jobs() -> None:
    page = _parse("hirehi", "https://hirehi.ru/")

    assert page.jobs == []


def test_krisp_careers_page_links_to_job_pages() -> None:
    page = _parse("krisp", "https://krisp.ai/careers/")

    assert len(page.jobs) >= 10
    assert all(url.startswith("https://krisp.ai/jobs/") for url in _urls(page))
    assert page.jobs[0] == ListingJob(
        url="https://krisp.ai/jobs/enterprise-abm-lead", title="Enterprise ABM Lead"
    )


def test_wrike_without_pattern_returns_only_jobs_subpages() -> None:
    page = _parse("wrike", "https://www.wrike.com/jobs/")

    # Wrike lists offices, not jobs; whatever comes back stays under /jobs/.
    assert all(url.startswith("https://www.wrike.com/jobs/") for url in _urls(page))
    assert "https://www.wrike.com/jobs" not in _urls(page)


# --- link rules (synthetic) -----------------------------------------------


def _html(body: str, head: str = "") -> str:
    return f"<html><head>{head}</head><body>{body}</body></html>"


def test_skips_non_http_fragment_and_foreign_links() -> None:
    html = _html(
        '<a href="mailto:hr@acme.com">/jobs/x</a>'
        '<a href="tel:+100">call</a>'
        '<a href="javascript:void(0)">js</a>'
        '<a href="#jobs/1">frag</a>'
        '<a href="ftp://acme.com/jobs/1">ftp</a>'
        '<a href="https://evil.com/jobs/1">foreign</a>'
        '<a href="https://notacme.com/jobs/1">lookalike</a>'
        '<a href="/jobs/2">Real job</a>'
    )

    page = parse_listing(html, "https://acme.com/careers", None)

    assert _urls(page) == ["https://acme.com/jobs/2"]


def test_accepts_same_host_and_subdomain_ignoring_www() -> None:
    html = _html(
        '<a href="https://jobs.acme.com/job/1">Sub</a>'
        '<a href="https://acme.com/job/2">Bare</a>'
        '<a href="https://www.acme.com/job/3">Www</a>'
    )

    page = parse_listing(html, "https://www.acme.com/open", None)

    assert _urls(page) == [
        "https://jobs.acme.com/job/1",
        "https://acme.com/job/2",
        "https://www.acme.com/job/3",
    ]


def test_accepts_parent_domain_but_not_sibling_subdomain() -> None:
    html = _html(
        '<a href="https://acme.com/job/1">Parent</a>'
        '<a href="https://blog.acme.com/job/2">Sibling</a>'
    )

    page = parse_listing(html, "https://careers.acme.com/open", None)

    assert _urls(page) == ["https://acme.com/job/1"]


def test_dedupes_by_normalized_url_and_keeps_page_order() -> None:
    html = _html(
        '<a href="/vacancies/b?utm_source=x">B</a>'
        '<a href="/vacancies/a">A</a>'
        '<a href="/vacancies/b/#apply">B again</a>'
        '<a href="/vacancies/a/">A again</a>'
    )

    page = parse_listing(html, "https://acme.com/vacancies", None)

    assert page.jobs == [
        ListingJob(url="https://acme.com/vacancies/b", title="B"),
        ListingJob(url="https://acme.com/vacancies/a", title="A"),
    ]


@pytest.mark.parametrize(
    ("href", "is_job"),
    [
        ("/job/123", True),
        ("/en/jobs/backend-dev", True),
        ("/vakansii/frontend", True),
        ("/positions/42", True),
        ("/openings/abc", True),
        ("/careers/eng/sre", True),
        ("/roles/pm", True),
        ("/jobs", False),
        ("/jobs/", False),
        ("/jobs/vacancies", False),
        ("/job-backend-dev", False),
        ("/about/team", False),
        ("/jobsearch/1", False),
        ("/jobs/logo.png", False),
    ],
)
def test_job_like_path_needs_a_segment_after_the_job_word(
    href: str, is_job: bool
) -> None:
    page = parse_listing(
        _html(f'<a href="{href}">Title</a>'), "https://acme.com/", None
    )

    assert bool(page.jobs) is is_job


def test_listing_url_itself_is_not_a_job() -> None:
    html = _html('<a href="/careers/jobs/">All</a><a href="/careers/jobs/7">Seven</a>')

    page = parse_listing(html, "https://acme.com/careers/jobs", None)

    assert _urls(page) == ["https://acme.com/careers/jobs/7"]


def test_pattern_is_case_insensitive_and_untitled_link_gets_slug() -> None:
    html = _html(
        '<a href="/p/Backend-Dev"><img src="x.png"></a>'
        '<a href="/p/Other">Other</a>'
        '<a href="/blog/post">Blog</a>'
    )

    page = parse_listing(html, "https://acme.com/", "/P/")

    assert page.jobs == [
        ListingJob(url="https://acme.com/p/Backend-Dev", title="Backend-Dev"),
        ListingJob(url="https://acme.com/p/Other", title="Other"),
    ]


def test_without_pattern_untitled_links_are_dropped() -> None:
    html = _html('<a href="/job/1"><img src="x.png"></a>')

    assert parse_listing(html, "https://acme.com/", None).jobs == []


def test_title_from_title_or_aria_label_and_capped() -> None:
    long_title = "x" * 400
    html = _html(
        f'<a href="/job/1" title="  Data   Engineer ">  </a>'
        f'<a href="/job/2" aria-label="QA"></a>'
        f'<a href="/job/3">{long_title}</a>'
    )

    page = parse_listing(html, "https://acme.com/", None)

    assert [job.title for job in page.jobs] == [
        "Data Engineer",
        "QA",
        "x" * MAX_TITLE_CHARS,
    ]


def test_marked_title_wins_over_earlier_plain_text() -> None:
    html = _html(
        '<a href="/job/1">Berlin</a>'
        '<p class="vacancy-name"><a href="/job/1">Go Developer</a></p>'
        '<a href="/job/1">ACME GmbH</a>'
    )

    page = parse_listing(html, "https://acme.com/", None)

    assert page.jobs == [ListingJob(url="https://acme.com/job/1", title="Go Developer")]


def test_navigation_header_footer_and_pagination_links_skipped() -> None:
    html = _html(
        '<header><a href="/jobs/benefits">Benefits</a></header>'
        '<nav><a href="/jobs/teams">Teams</a></nav>'
        '<a href="/jobs/backend" role="option">Backend</a>'
        '<main><a href="/jobs/42-go-dev">Go dev</a>'
        '<a href="/jobs/2">2</a>'
        '<ul class="pagination"><a href="/jobs/3"><i>chevron_right</i></a></ul></main>'
        '<footer><a href="/jobs/blog">Blog</a></footer>'
    )

    page = parse_listing(html, "https://acme.com/jobs", None)

    assert _urls(page) == ["https://acme.com/jobs/42-go-dev"]


# --- next page (synthetic) ----------------------------------------------------


def test_next_from_link_rel_next() -> None:
    html = _html("", head='<link rel="next" href="/jobs?page=5">')

    page = parse_listing(html, "https://acme.com/jobs?page=4", None)

    assert page.next_url == "https://acme.com/jobs?page=5"


def test_next_from_anchor_rel_next_ignores_foreign_host() -> None:
    html = _html(
        '<a rel="nofollow next" href="https://evil.com/jobs?page=2">evil</a>'
        '<a class="pager" rel="next" href="/openings/all/?offset=20">More</a>'
    )

    page = parse_listing(html, "https://acme.com/openings/all", None)

    assert page.next_url == "https://acme.com/openings/all?offset=20"


@pytest.mark.parametrize(
    ("page_url", "links", "expected"),
    [
        (
            "https://acme.com/jobs",
            ["/jobs?page=3", "/other?page=2", "/jobs?page=2"],
            "https://acme.com/jobs?page=2",
        ),
        (
            "https://acme.com/jobs?page=2",
            ["/jobs?page=1", "/jobs?page=3"],
            "https://acme.com/jobs?page=3",
        ),
        (
            "https://acme.com/jobs?p=7",
            ["/jobs?p=8&sort=new"],
            "https://acme.com/jobs?p=8&sort=new",
        ),
        ("https://acme.com/jobs", ["/jobs?page=1"], None),
        ("https://acme.com/jobs", ["https://evil.com/jobs?page=2"], None),
    ],
)
def test_next_from_page_query_param(
    page_url: str, links: list[str], expected: str | None
) -> None:
    html = _html("".join(f'<a href="{href}">n</a>' for href in links))

    assert parse_listing(html, page_url, None).next_url == expected


def test_no_jobs_and_no_next_on_empty_page() -> None:
    assert parse_listing("", "https://acme.com/", None) == ListingPage(
        jobs=[], next_url=None
    )
