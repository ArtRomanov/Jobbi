import pytest

from app.services.vacancy_source_parsing import (
    BOARD_INVALID_INPUT_MESSAGE,
    INVALID_INPUT_MESSAGE,
    MAX_INPUT_LENGTH,
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
        "https://t.me/joinchat/AAAAAE",
        "https://t.me/+AbCdEfGhIj",
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
        "https://boards.greenhouse.io/\u0430cme",  # Cyrillic a in the token
    ],
)
def test_hostile_or_unknown_board_links_rejected(raw: str) -> None:
    with pytest.raises(SourceInputError) as exc_info:
        parse_source_input(raw)
    assert exc_info.value.message == BOARD_INVALID_INPUT_MESSAGE


@pytest.mark.parametrize(
    "raw",
    [
        "jobs.lever.co.evil.com/acme",
        "https://jobs.lever.co.evil.com/acme",
        "https://jobs.eu.lever.co.evil.com/acme",
        "https://boards.greenhouse.io.evil.com/acme",
        "https://evil.com/jobs.lever.co/acme",
        "evil.com/boards.greenhouse.io/acme",
        "https://evil.com/?u=jobs.lever.co/acme",
        "https://jobs.lever.co@evil.com/acme",
        "https://jobs.lever.c\u043e/acme",  # Cyrillic o in the host
        "https://evil.com/durov_jobs",
        "https://example.com/careers",
        "http://localhost:8000/admin",
        "https://169.254.169.254/latest/meta-data",
    ],
)
def test_board_lookalikes_on_other_hosts_get_no_board_hint(raw: str) -> None:
    # The board hint follows the parsed host, not a substring of the text.
    with pytest.raises(SourceInputError) as exc_info:
        parse_source_input(raw)
    assert exc_info.value.message == INVALID_INPUT_MESSAGE


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        # The parsed host is a board domain -> board hint.
        ("boards.greenhouse.io/", BOARD_INVALID_INPUT_MESSAGE),
        ("x.teamtailor.com:443", BOARD_INVALID_INPUT_MESSAGE),
        # A board domain elsewhere in the text, or another host -> no board hint.
        ("jobs.lever.co.evil.com/acme", INVALID_INPUT_MESSAGE),
        ("https://example.com/x", INVALID_INPUT_MESSAGE),
        ("clever.com/careers", INVALID_INPUT_MESSAGE),
        ("https://clever.com/careers", INVALID_INPUT_MESSAGE),
        ("https://www.clever.co/jobs", INVALID_INPUT_MESSAGE),
        ("notgreenhouse.io/acme", INVALID_INPUT_MESSAGE),
        ("myteamtailor.com/jobs", INVALID_INPUT_MESSAGE),
        # Telegram-looking input -> Telegram hint.
        ("@abc", INVALID_INPUT_MESSAGE),
        ("t.me/abc", INVALID_INPUT_MESSAGE),
        ("https://t.me/joinchat/AAAAAE", INVALID_INPUT_MESSAGE),
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


# --- Teamtailor boards -------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "approvalmax.teamtailor.com",
        "approvalmax.teamtailor.com/",
        "https://approvalmax.teamtailor.com",
        "http://approvalmax.teamtailor.com/jobs",
        "https://ApprovalMax.teamtailor.com/jobs",
        "HTTPS://APPROVALMAX.TEAMTAILOR.COM/JOBS",
        "https://approvalmax.teamtailor.com/jobs/8683780-director-of-product",
        "https://approvalmax.teamtailor.com/jobs.rss",
        "https://approvalmax.teamtailor.com/jobs?department=sales&loc=1",
        "  https://approvalmax.teamtailor.com/jobs  ",
    ],
)
def test_teamtailor_forms_accepted(raw: str) -> None:
    assert parse_source_input(raw) == ParsedSource(
        kind="teamtailor", handle="approvalmax"
    )


@pytest.mark.parametrize("sub", ["a", "a1", "acme-labs", "1acme", "x" * 63])
def test_teamtailor_subdomain_bounds_accepted(sub: str) -> None:
    parsed = parse_source_input(f"https://{sub}.teamtailor.com/jobs")
    assert parsed == ParsedSource(kind="teamtailor", handle=sub)


@pytest.mark.parametrize(
    "raw",
    [
        # Board host, but not a usable board reference -> board hint.
        "teamtailor.com",
        "https://teamtailor.com/jobs",
        "https://www.teamtailor.com/en",
        "https://app.teamtailor.com/companies/1",
        "https://api.teamtailor.com/v1/jobs",
        "https://a.b.teamtailor.com/jobs",
        "https://-acme.teamtailor.com",
        "https://acme-.teamtailor.com",
        "https://acme_labs.teamtailor.com",
        "https://" + "x" * 64 + ".teamtailor.com",
        "a@x.teamtailor.com",
        "https://a@x.teamtailor.com/jobs",
        "https://x.teamtailor.com:443/jobs",
        "x.teamtailor.com:8080",
        "https://x.teamtailor.com.:443/jobs",
        "ftp://x.teamtailor.com/jobs",
        "javascript://x.teamtailor.com/jobs",
        "//x.teamtailor.com/jobs",
        "https://x.teamtailor.com/jobs#frag",
        "https://x.teamtailor.com/jo bs",
        "https://x.teamtailor.com/<script>",
        "https://K.teamtailor.com/jobs",  # Kelvin sign
        "https://x.teamtailor.com/" + "a" * 501,
    ],
)
def test_teamtailor_bad_links_get_board_hint(raw: str) -> None:
    with pytest.raises(SourceInputError) as exc_info:
        parse_source_input(raw)
    assert exc_info.value.message == BOARD_INVALID_INPUT_MESSAGE


@pytest.mark.parametrize(
    "raw",
    [
        "teamtailor.com.evil.com",
        "https://teamtailor.com.evil.com/jobs",
        "evil.com/teamtailor.com",
        "https://evil.com/x.teamtailor.com",
        "x.teamtailor.com.evil.com",
        "https://x.teamtailor.com.evil.com/jobs",
        "https://x.teamtailor.com@evil.com/jobs",
        "https://evil.com/?u=x.teamtailor.com",
        "https://xteamtailor.com/jobs",
        "https://x.teamtailor.co/jobs",
        "https://x.teamtailor.com-evil.com/jobs",
        "https://x.teamtai1or.com/jobs",
        "https://x.teamtailоr.com/jobs",  # Cyrillic o in the host
        "https://аcme.teamtailor.com.evil.com/jobs",  # Cyrillic a
    ],
)
def test_teamtailor_lookalikes_rejected_without_board_hint(raw: str) -> None:
    with pytest.raises(SourceInputError) as exc_info:
        parse_source_input(raw)
    assert exc_info.value.message == INVALID_INPUT_MESSAGE


def test_teamtailor_unicode_subdomain_is_not_a_board() -> None:
    # A non-ASCII subdomain never becomes a handle (the host still gets the hint).
    with pytest.raises(SourceInputError):
        parse_source_input("https://аcme.teamtailor.com/jobs")
