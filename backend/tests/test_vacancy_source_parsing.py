import pytest

from app.services.vacancy_source_parsing import (
    BOARD_INVALID_INPUT_MESSAGE,
    INVALID_INPUT_MESSAGE,
    MAX_INPUT_LENGTH,
    PRIVATE_INVITE_MESSAGE,
    ParsedSource,
    SourceInputError,
    parse_source_input,
)


@pytest.mark.parametrize(
    "raw",
    [
        "@durov_jobs",
        "durov_jobs",
        "Durov_Jobs",
        "@DUROV_JOBS",
        "  @durov_jobs  ",
        "t.me/durov_jobs",
        "t.me/durov_jobs/",
        "https://t.me/durov_jobs",
        "http://t.me/durov_jobs",
        "HTTPS://T.ME/Durov_Jobs",
        "t.me/s/durov_jobs",
        "https://t.me/s/durov_jobs",
        "https://t.me/s/durov_jobs/",
        "https://t.me/durov_jobs/123",
        "https://t.me/s/durov_jobs/123",
        "https://t.me/durov_jobs/123?single",
        "https://t.me/s/durov_jobs?before=500",
    ],
)
def test_telegram_forms_accepted(raw: str) -> None:
    assert parse_source_input(raw) == ParsedSource(kind="telegram", handle="durov_jobs")


@pytest.mark.parametrize("handle", ["abcde", "a" * 32, "12345", "a_b_c"])
def test_telegram_handle_length_bounds_accepted(handle: str) -> None:
    assert parse_source_input(f"@{handle}").handle == handle.lower()


@pytest.mark.parametrize(
    "raw",
    [
        # Empty / too short / too long handles
        "",
        "   ",
        "@",
        "@abcd",
        "t.me/abcd",
        "@" + "a" * 33,
        "t.me/s/" + "a" * 33,
        # Other hosts and look-alikes
        "https://t.me.evil.com/durov_jobs",
        "t.me.evil.com/durov_jobs",
        "evil.com/t.me/durov_jobs",
        "https://evilt.me/durov_jobs",
        "https://www.t.me/durov_jobs",
        "https://telegram.me/durov_jobs",
        "https://user@t.me/durov_jobs",
        "https://t.me@evil.com/durov_jobs",
        "https://t.me:8080/durov_jobs",
        "//t.me/durov_jobs",
        "ftp://t.me/durov_jobs",
        "javascript:alert(1)",
        "javascript://t.me/durov_jobs",
        "file:///etc/passwd",
        # Path traversal / extra path segments
        "t.me/../durov_jobs",
        "t.me/s/../../etc/passwd",
        "https://t.me/durov_jobs/../admin",
        "https://t.me/durov_jobs/abc",
        "https://t.me/durov_jobs#frag",
        "https://t.me/durov_jobs%2F..",
        "t.me/s/s/durov_jobs",
        # Whitespace / control characters inside
        "@durov jobs",
        "t.me/ durov_jobs",
        "@durov_jobs\n@other_one",
        "@durov\tjobs",
        "@durov_jobs\x00",
        # Non-ASCII look-alikes (Kelvin sign, Cyrillic a, long s)
        "@Kelvin_jobs",
        "t.me/Kelvin_jobs",
        "t.me/ſome_jobs",
        "@durоv_jobs",
        # Not channels
        "durov.jobs",
        "@durov-jobs",
    ],
)
def test_hostile_or_unsupported_input_rejected(raw: str) -> None:
    with pytest.raises(SourceInputError) as exc_info:
        parse_source_input(raw)
    assert exc_info.value.message == INVALID_INPUT_MESSAGE


@pytest.mark.parametrize(
    "raw",
    [
        "https://t.me/+0zv_MNh22Xw3NTMy",
        "t.me/+0zv_MNh22Xw3NTMy",
        "http://t.me/joinchat/AAAAAEtest123",
        "https://telegram.me/joinchat/AAAAAEtest123",
        "T.ME/+abc",
    ],
)
def test_private_invite_link_gets_private_hint(raw: str) -> None:
    with pytest.raises(SourceInputError) as exc_info:
        parse_source_input(raw)
    assert exc_info.value.message == PRIVATE_INVITE_MESSAGE


def test_over_long_input_rejected() -> None:
    raw = "https://t.me/s/durov_jobs/" + "1" * MAX_INPUT_LENGTH
    with pytest.raises(SourceInputError):
        parse_source_input(raw)


# --- Greenhouse / Lever boards ---------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "boards.greenhouse.io/acme",
        "job-boards.greenhouse.io/acme",
        "boards.eu.greenhouse.io/acme",
        "job-boards.eu.greenhouse.io/acme",
        "https://boards.greenhouse.io/acme",
        "http://boards.greenhouse.io/acme",
        "https://job-boards.greenhouse.io/acme/",
        "https://job-boards.eu.greenhouse.io/Acme",
        "HTTPS://BOARDS.GREENHOUSE.IO/ACME",
        "https://boards.greenhouse.io/acme/jobs/4012345",
        "https://job-boards.eu.greenhouse.io/acme/jobs/4012345/",
        "https://job-boards.greenhouse.io/acme/jobs/4012345?gh_jid=4012345",
        "https://boards.greenhouse.io/acme?gh_src=abc.1",
        "  https://boards.greenhouse.io/acme  ",
    ],
)
def test_greenhouse_forms_accepted(raw: str) -> None:
    assert parse_source_input(raw) == ParsedSource(kind="greenhouse", handle="acme")


@pytest.mark.parametrize("token", ["a", "acme_labs", "acme-labs", "a1", "x" * 64])
def test_greenhouse_token_bounds_accepted(token: str) -> None:
    parsed = parse_source_input(f"https://boards.greenhouse.io/{token}")
    assert parsed == ParsedSource(kind="greenhouse", handle=token)


POSTING_ID = "065f4538-7347-4207-909f-4ea68f63b4af"


@pytest.mark.parametrize(
    "raw",
    [
        "jobs.lever.co/acme-labs",
        "https://jobs.lever.co/acme-labs",
        "http://jobs.lever.co/acme-labs/",
        "https://jobs.lever.co/Acme-Labs",
        "HTTPS://JOBS.LEVER.CO/ACME-LABS",
        f"https://jobs.lever.co/acme-labs/{POSTING_ID}",
        f"https://jobs.lever.co/acme-labs/{POSTING_ID}/",
        f"https://jobs.lever.co/acme-labs/{POSTING_ID}/apply",
        "https://jobs.lever.co/acme-labs?lever-source=linkedin",
    ],
)
def test_lever_forms_accepted(raw: str) -> None:
    assert parse_source_input(raw) == ParsedSource(kind="lever", handle="acme-labs")


@pytest.mark.parametrize(
    "raw",
    [
        "jobs.eu.lever.co/acme",
        "https://jobs.eu.lever.co/acme/",
        "https://JOBS.EU.LEVER.CO/Acme",
        f"https://jobs.eu.lever.co/acme/{POSTING_ID}",
    ],
)
def test_lever_eu_forms_accepted(raw: str) -> None:
    assert parse_source_input(raw) == ParsedSource(kind="lever_eu", handle="acme")


@pytest.mark.parametrize(
    "raw",
    [
        # Look-alike hosts
        "jobs.lever.co.evil.com/acme",
        "https://jobs.lever.co.evil.com/acme",
        "https://jobs.eu.lever.co.evil.com/acme",
        "https://boards.greenhouse.io.evil.com/acme",
        "https://evil.com/jobs.lever.co/acme",
        "evil.com/boards.greenhouse.io/acme",
        "https://evil.com/?u=jobs.lever.co/acme",
        "https://eviljobs.lever.co/acme",
        "https://xboards.greenhouse.io/acme",
        # Other subdomains / hosts of the same companies
        "https://api.lever.co/v0/postings/acme",
        "https://api.eu.lever.co/v0/postings/acme",
        "https://boards-api.greenhouse.io/v1/boards/acme",
        "https://www.greenhouse.io/acme",
        "https://jobs.us.lever.co/acme",
        "https://boards.us.greenhouse.io/acme",
        "https://lever.co/acme",
        "https://greenhouse.io/acme",
        # Userinfo and ports
        "https://user@jobs.lever.co/acme",
        "https://jobs.lever.co@evil.com/acme",
        "https://boards.greenhouse.io:8443/acme",
        "https://jobs.lever.co:443/acme",
        # Schemes
        "ftp://jobs.lever.co/acme",
        "//boards.greenhouse.io/acme",
        "javascript://boards.greenhouse.io/acme",
        # Paths
        "https://boards.greenhouse.io/",
        "https://boards.greenhouse.io",
        "https://jobs.lever.co/",
        "https://boards.greenhouse.io/../admin",
        "https://boards.greenhouse.io/acme/../../v1",
        "https://boards.greenhouse.io/acme%2F..",
        "https://boards.greenhouse.io/acme/jobs/abc",
        "https://boards.greenhouse.io/acme/admin",
        "https://boards.greenhouse.io/embed/job_board?for=acme",
        "https://jobs.lever.co/acme/not-a-posting-id",
        "https://jobs.lever.co/acme/" + POSTING_ID + "/edit",
        "https://jobs.lever.co/acme#frag",
        "https://boards.greenhouse.io/acme.labs",
        "https://boards.greenhouse.io/" + "x" * 65,
        # Whitespace and non-ASCII look-alikes
        "https://jobs.lever.co/ac me",
        "https://jobs.lever.co/ac\nme",
        "https://jobs.lever.co/\u212acme",  # Kelvin sign
        "https://jobs.lever.c\u043e/acme",  # Cyrillic o in the host
        "https://boards.greenhouse.io/\u0430cme",  # Cyrillic a in the token
        # Not boards at all
        "https://evil.com/durov_jobs",
        "https://example.com/careers",
        "http://localhost:8000/admin",
        "https://169.254.169.254/latest/meta-data",
    ],
)
def test_hostile_or_unknown_board_links_rejected(raw: str) -> None:
    with pytest.raises(SourceInputError) as exc_info:
        parse_source_input(raw)
    assert exc_info.value.message == BOARD_INVALID_INPUT_MESSAGE


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        # Mentions a board domain -> board hint, wherever it appears.
        ("jobs.lever.co.evil.com/acme", BOARD_INVALID_INPUT_MESSAGE),
        ("boards.greenhouse.io/", BOARD_INVALID_INPUT_MESSAGE),
        # An http(s) URL on a host that does not look like Telegram -> board hint.
        ("https://example.com/x", BOARD_INVALID_INPUT_MESSAGE),
        # Telegram-looking input -> Telegram hint.
        ("@abc", INVALID_INPUT_MESSAGE),
        ("t.me/abc", INVALID_INPUT_MESSAGE),
        ("https://t.me/joinchat/AAAAAE", PRIVATE_INVITE_MESSAGE),
        ("https://t.me.evil.com/durov_jobs", INVALID_INPUT_MESSAGE),
        ("https://telegram.me/durov_jobs", INVALID_INPUT_MESSAGE),
        ("@clever_jobs!", INVALID_INPUT_MESSAGE),  # "lever" inside is not a link
        # Anything else without a scheme -> Telegram hint.
        ("durov.jobs", INVALID_INPUT_MESSAGE),
        ("javascript:alert(1)", INVALID_INPUT_MESSAGE),
    ],
)
def test_error_hint_follows_what_the_input_looks_like(raw: str, message: str) -> None:
    with pytest.raises(SourceInputError) as exc_info:
        parse_source_input(raw)
    assert exc_info.value.message == message


def test_bare_word_is_still_a_telegram_channel() -> None:
    # A bare word is never guessed to be a board.
    assert parse_source_input("acmelabs").kind == "telegram"
