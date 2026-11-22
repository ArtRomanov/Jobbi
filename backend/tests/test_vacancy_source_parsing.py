import pytest

from app.services.vacancy_source_parsing import (
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
        "https://evil.com/durov_jobs",
        "https://t.me.evil.com/durov_jobs",
        "t.me.evil.com/durov_jobs",
        "evil.com/t.me/durov_jobs",
        "https://evil.com/?u=t.me/durov_jobs",
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
        # Board links are not supported until Slice 6
        "https://boards.greenhouse.io/acme",
        "https://jobs.lever.co/acme",
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
