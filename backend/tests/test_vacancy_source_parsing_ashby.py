"""Ashby board links (spec 010 §2.6): accepted forms, board hint, look-alikes."""

import pytest

from app.services.vacancy_source_parsing import (
    BOARD_INVALID_INPUT_MESSAGE,
    ParsedSource,
    SourceInputError,
    parse_source_input,
)

JOB_UUID = "72eaca21-1d04-4e08-ac70-c987519dda1f"


def test_board_error_text_names_ashby() -> None:
    assert BOARD_INVALID_INPUT_MESSAGE == (
        "Not a Greenhouse, Lever, Teamtailor or Ashby job board link"
    )


@pytest.mark.parametrize(
    "raw",
    [
        "jobs.ashbyhq.com/manychat",
        "jobs.ashbyhq.com/manychat/",
        "https://jobs.ashbyhq.com/manychat",
        "http://jobs.ashbyhq.com/manychat",
        "HTTPS://JOBS.ASHBYHQ.COM/Manychat",
        f"https://jobs.ashbyhq.com/manychat/{JOB_UUID}",
        f"https://jobs.ashbyhq.com/manychat/{JOB_UUID}/",
        f"https://jobs.ashbyhq.com/manychat/{JOB_UUID}/application",
        f"https://jobs.ashbyhq.com/manychat/{JOB_UUID.upper()}",
        "https://jobs.ashbyhq.com/manychat?departmentId=abc-1",
        "https://jobs.ashbyhq.com/manychat?utm_source=linkedin",
        f"https://jobs.ashbyhq.com/manychat/{JOB_UUID}?src=x",
        "  https://jobs.ashbyhq.com/manychat  ",
    ],
)
def test_ashby_forms_accepted(raw: str) -> None:
    assert parse_source_input(raw) == ParsedSource(kind="ashby", handle="manychat")


@pytest.mark.parametrize(
    ("org", "handle"),
    [
        ("a", "a"),
        ("Kraken.com", "kraken.com"),  # a real board slug with a dot
        ("acme-labs", "acme-labs"),
        ("acme_labs", "acme_labs"),
        ("1password", "1password"),
        ("a" * 64, "a" * 64),
    ],
)
def test_ashby_org_bounds_accepted(org: str, handle: str) -> None:
    parsed = parse_source_input(f"https://jobs.ashbyhq.com/{org}")
    assert parsed == ParsedSource(kind="ashby", handle=handle)


@pytest.mark.parametrize(
    "raw",
    [
        "ashbyhq.com",
        "https://ashbyhq.com/manychat",
        "https://www.ashbyhq.com/customers",
        "https://app.ashbyhq.com/manychat",
        "https://api.ashbyhq.com/posting-api/job-board/manychat",
        "https://jobs.ashbyhq.com",
        "https://jobs.ashbyhq.com/",
        "https://jobs.ashbyhq.com/" + "a" * 65,
        "https://jobs.ashbyhq.com/-acme",
        "https://jobs.ashbyhq.com/acme-",
        "https://jobs.ashbyhq.com/.acme",
        "https://jobs.ashbyhq.com/acme.",
        "https://jobs.ashbyhq.com/a..b",
        "https://jobs.ashbyhq.com/..",
        "https://jobs.ashbyhq.com/acme%2F..%2Fx",
        "https://jobs.ashbyhq.com/acme/../evil",
        "https://jobs.ashbyhq.com/acme/not-a-uuid",
        "https://jobs.ashbyhq.com/acme/embed",
        "https://jobs.ashbyhq.com/embed",
        "https://jobs.ashbyhq.com/api",
        "https://jobs.ashbyhq.com/a@b",
        "a@jobs.ashbyhq.com/acme",
        "https://a@jobs.ashbyhq.com/acme",
        "https://jobs.ashbyhq.com:443/acme",
        "jobs.ashbyhq.com:8080/acme",
        "//jobs.ashbyhq.com/acme",
        "https://jobs.ashbyhq.com/ac me",
        "https://jobs.ashbyhq.com/<script>",
        "https://jobs.ashbyhq.com/Kcme",  # Kelvin sign
        "https://jobs.ashbyhq.com/аcme",  # Cyrillic a
        "https://jobs.eu.ashbyhq.com/acme",
    ],
)
def test_ashby_bad_links_get_board_hint(raw: str) -> None:
    with pytest.raises(SourceInputError) as exc_info:
        parse_source_input(raw)
    assert exc_info.value.message == BOARD_INVALID_INPUT_MESSAGE


@pytest.mark.parametrize(
    "raw",
    [
        "jobs.ashbyhq.com.evil.com/manychat",
        "https://jobs.ashbyhq.com.evil.com/manychat",
        "https://evil.com/jobs.ashbyhq.com/manychat",
        "https://evil.com/?u=jobs.ashbyhq.com/manychat",
        "https://jobsashbyhq.com/manychat",
        "https://jobs.ashbyhq.co/manychat",
        "https://jobs.ashbyhq.com-evil.com/manychat",
        "https://jobs.ashbyhg.com/manychat",
        "https://jobs.аshbyhq.com/manychat",  # Cyrillic a in the host
    ],
)
def test_ashby_lookalikes_are_web_pages_not_boards(raw: str) -> None:
    assert parse_source_input(raw).kind == "web"
