"""Tests for the listing page parser (saved real pages + small synthetic ones)."""

from pathlib import Path

import pytest

from app.discovery.fetchers.web_listing import (
    MAX_TITLE_CHARS,
    AtsHint,
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


# --- ATS hint -----------------------------------------------------------------

GREENHOUSE_WRIKE = AtsHint(
    kind="greenhouse",
    input="https://job-boards.greenhouse.io/wrike",
    label="Greenhouse",
)


def _hint(body: str, page_url: str = "https://example.com/careers") -> AtsHint | None:
    return parse_listing(f"<html><body>{body}</body></html>", page_url, None).ats_hint


def test_wrike_page_hints_its_greenhouse_board() -> None:
    page = _parse("wrike", "https://www.wrike.com/jobs/")

    assert page.ats_hint == GREENHOUSE_WRIKE


@pytest.mark.parametrize(
    "fixture,page_url",
    [
        ("geekjob", "https://geekjob.ru/vacancies"),
        ("hirehi", "https://hirehi.ru/"),
    ],
)
def test_page_without_board_links_has_no_hint(fixture: str, page_url: str) -> None:
    assert _parse(fixture, page_url).ats_hint is None


@pytest.mark.parametrize(
    "body",
    [
        '<a href="https://boards.greenhouse.io/embed/job_board?for=Wrike">Jobs</a>',
        '<iframe src="https://job-boards.greenhouse.io/embed/job_board?for=wrike&b=x">'
        "</iframe>",
        '<a href="//boards.greenhouse.io/embed/job_app?for=wrike&token=4238976005">'
        "Apply</a>",
        '<script src="https://boards.greenhouse.io/embed/job_board/js?for=wrike">'
        "</script>",
        '<a href="https://boards.eu.greenhouse.io/wrike/jobs/4238976005#apply">Job</a>',
    ],
)
def test_greenhouse_links_and_embeds_give_the_board_token(body: str) -> None:
    assert _hint(body) == GREENHOUSE_WRIKE


@pytest.mark.parametrize(
    "body",
    [
        '<a href="https://boards.greenhouse.io/embed/job_board">Jobs</a>',
        '<a href="https://boards.greenhouse.io/embed/job_board?for=embed">Jobs</a>',
        '<a href="https://boards.greenhouse.io/embed/job_board?for=a/b">Jobs</a>',
        '<a href="https://evil.com/embed/job_board?for=wrike">Jobs</a>',
        '<a href="https://www.greenhouse.io/careers">Greenhouse careers</a>',
        '<a href="https://jobs.lever.co.evil.com/acme">Look-alike</a>',
        '<a href="https://t.me/acme_jobs">Telegram</a>',
        '<a href="mailto:jobs@acme.com">Mail</a>',
    ],
)
def test_non_board_links_give_no_hint(body: str) -> None:
    assert _hint(body) is None


def test_lever_board_hint() -> None:
    body = (
        '<a href="https://jobs.lever.co/Acme/0b5c6a1e-1234-4abc-9def-0123456789ab">'
        "Job</a>"
        '<a href="https://jobs.lever.co/acme?team=Eng">All jobs</a>'
    )

    assert _hint(body) == AtsHint(
        kind="lever", input="https://jobs.lever.co/acme", label="Lever"
    )


def test_lever_eu_board_hint() -> None:
    assert _hint('<a href="https://jobs.eu.lever.co/acme">Jobs</a>') == AtsHint(
        kind="lever_eu", input="https://jobs.eu.lever.co/acme", label="Lever"
    )


def test_teamtailor_board_hint() -> None:
    body = '<a href="https://acme.teamtailor.com/jobs/123-react-dev">React dev</a>'

    assert _hint(body) == AtsHint(
        kind="teamtailor", input="https://acme.teamtailor.com", label="Teamtailor"
    )


def test_most_linked_board_wins() -> None:
    body = (
        '<a href="https://acme.teamtailor.com/jobs/1">One</a>'
        '<a href="https://jobs.lever.co/acme">Lever</a>'
        '<a href="https://acme.teamtailor.com/jobs/2">Two</a>'
    )

    assert _hint(body) == AtsHint(
        kind="teamtailor", input="https://acme.teamtailor.com", label="Teamtailor"
    )


def test_tie_goes_to_the_first_board_seen() -> None:
    body = (
        '<a href="https://jobs.lever.co/acme">Lever</a>'
        '<a href="https://acme.teamtailor.com/jobs/1">Teamtailor</a>'
    )

    assert _hint(body) == AtsHint(
        kind="lever", input="https://jobs.lever.co/acme", label="Lever"
    )


def test_relative_link_on_a_board_host_counts() -> None:
    assert _hint('<a href="/jobs/1">Job</a>', "https://acme.teamtailor.com/jobs") == (
        AtsHint(
            kind="teamtailor", input="https://acme.teamtailor.com", label="Teamtailor"
        )
    )


# --- hostile input ------------------------------------------------------------

PAGE = "https://example.com/careers"


@pytest.mark.parametrize(
    "body",
    [
        pytest.param('<a href="http://[broken/jobs/1">Broken</a>', id="bad-ipv6-host"),
        pytest.param('<a href="https://[::1/jobs/2">Broken</a>', id="unclosed-bracket"),
        pytest.param('<a href="//[x]:99999/jobs/3">Port</a>', id="bad-port"),
        pytest.param('<a href="/jobs/\ud800">Surrogate</a>', id="surrogate"),
        pytest.param('<link rel="next" href="http://[broken">', id="bad-next"),
        pytest.param("<div>" * 100_000 + "</div>" * 100_000, id="very-deep"),
    ],
)
def test_hostile_links_do_not_raise(body: str) -> None:
    html = f'<html><body>{body}<a href="/jobs/ok"><h3>Fine</h3></a></body></html>'

    page = parse_listing(html, PAGE, None)

    assert isinstance(page, ListingPage)


def test_broken_link_is_skipped_and_others_kept() -> None:
    html = (
        '<a href="http://[broken/jobs/1">Broken</a>'
        '<a href="/jobs/ok"><h3>Fine</h3></a>'
    )

    page = parse_listing(html, PAGE, None)

    assert page.jobs == [ListingJob(url="https://example.com/jobs/ok", title="Fine")]


def test_chrome_detection_still_skips_nested_nav_and_pager() -> None:
    html = (
        '<nav><div><ul><li><a href="/jobs/nav1">Nav job</a></li></ul></div></nav>'
        '<div class="pagination"><span><a href="/jobs/p1">Pager job</a></span></div>'
        '<a role="tab" href="/jobs/tab1">Tab</a>'
        '<a class="pager" href="/jobs/self-pager">Self pager</a>'
        '<main><a href="/jobs/real"><h3>Real</h3></a></main>'
    )

    page = parse_listing(html, PAGE, None)

    assert [job.url for job in page.jobs] == ["https://example.com/jobs/real"]


def test_page_over_the_element_cap_gives_no_jobs() -> None:
    html = "<span></span>" * 210_000 + '<a href="/jobs/1"><h3>Job</h3></a>'

    assert parse_listing(html, PAGE, None).jobs == []


def _timed_parse(html: str) -> float:
    import time

    started = time.perf_counter()
    parse_listing(html, PAGE, None)
    return time.perf_counter() - started


def test_deep_page_with_many_anchors_is_fast() -> None:
    anchors = "".join(f'<a href="/jobs/{i}"><h3>Job {i}</h3></a>' for i in range(4_000))
    html = "<div>" * 2_000 + anchors + "</div>" * 2_000

    assert _timed_parse(html) < 1.5


def test_flat_page_with_150k_anchors_is_fast() -> None:
    html = '<a href="/jobs/1">x</a>' * 150_000

    assert _timed_parse(html) < 5.0


def test_nested_anchors_are_fast() -> None:
    html = '<a href="/jobs/1">x' * 3_000 + "</a>" * 3_000

    assert _timed_parse(html) < 1.5


def test_parse_listing_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.discovery.fetchers import web_listing

    def _boom(*args: object, **kwargs: object) -> None:
        raise RecursionError("too deep")

    monkeypatch.setattr(web_listing, "_anchor_title", _boom)

    page = parse_listing('<a href="/jobs/1"><h3>Job</h3></a>', PAGE, None)

    assert page.jobs == []
