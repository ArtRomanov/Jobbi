import pytest

from app.discovery.normalize import is_http_url, normalize_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("HTTPS://Jobs.Example.COM/Careers/1", "https://jobs.example.com/Careers/1"),
        ("https://example.com/job/", "https://example.com/job"),
        ("https://example.com/", "https://example.com"),
        ("https://example.com/job#apply", "https://example.com/job"),
        (
            "https://example.com/job?utm_source=tg&id=5&UTM_Medium=x&ref=a",
            "https://example.com/job?id=5&ref=a",
        ),
        ("https://example.com/job?utm_source=tg", "https://example.com/job"),
        ("https://example.com:443/job", "https://example.com/job"),
        ("http://example.com:80/job", "http://example.com/job"),
        ("https://example.com:8443/job", "https://example.com:8443/job"),
        ("https://user:pass@example.com/job", "https://example.com/job"),
        ("  https://example.com/job  ", "https://example.com/job"),
    ],
)
def test_normalize_url(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


def test_equivalent_links_normalize_equal() -> None:
    a = "https://Boards.Greenhouse.io/acme/jobs/42/?utm_campaign=x#top"
    b = "https://boards.greenhouse.io/acme/jobs/42"
    assert normalize_url(a) == normalize_url(b)


@pytest.mark.parametrize(
    "raw", ["not a url", "/relative/path", "mailto:jobs@example.com"]
)
def test_non_absolute_input_is_returned_stripped(raw: str) -> None:
    assert normalize_url(f" {raw} ") == raw


def test_invalid_port_does_not_raise() -> None:
    assert normalize_url("https://example.com:99999/x") == "https://example.com:99999/x"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://jobs.example.com/1", True),
        ("http://jobs.example.com/1", True),
        ("HTTPS://Jobs.Example.com/1", True),
        ("  https://jobs.example.com/1  ", True),
        ("javascript:alert(1)", False),
        ("JavaScript:alert(1)", False),
        ("data:text/html,<script>alert(1)</script>", False),
        ("/jobs/1", False),
        ("jobs.example.com/1", False),
        ("//jobs.example.com/1", False),
        ("https://", False),
        ("ftp://jobs.example.com/1", False),
        ("https://[::1", False),
        ("", False),
    ],
)
def test_is_http_url(url: str, expected: bool) -> None:
    assert is_http_url(url) is expected
