"""Turn what the user typed into a (kind, handle) pair.

The user's text is never fetched. It is only matched against strict, anchored
patterns; the handle extracted here is later combined with a fixed host
(`https://t.me/s/<handle>`), so look-alike hosts or odd paths cannot steer a
request anywhere else (no SSRF).

Supported inputs:
- Telegram: `@name`, `name`, `t.me/name`, `t.me/s/name` -> kind `telegram`.
- Greenhouse: `boards.greenhouse.io/<token>`, `job-boards.greenhouse.io/<token>`
  and their `.eu.` variants -> kind `greenhouse` (EU tokens are served by the
  standard API host, so the region is not stored).
- Lever: `jobs.lever.co/<company>` -> `lever`, `jobs.eu.lever.co/<company>` ->
  `lever_eu` (Lever keeps a company's data in one region).
- Teamtailor: `<sub>.teamtailor.com[/any path]` -> `teamtailor`, handle `<sub>`;
  only `https://<sub>.teamtailor.com/jobs.rss` is ever requested.

Which error text an unrecognised input gets (`_invalid_input_message`):
- its parsed host is, or ends with, `.greenhouse.io`, `.lever.co` or
  `.teamtailor.com` -> BOARD_INVALID_INPUT_MESSAGE (a host check, not a
  substring search, so `clever.com/careers` is not taken for a Lever link);
- anything else -> INVALID_INPUT_MESSAGE (the Telegram hint).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

MAX_INPUT_LENGTH = 200

INVALID_INPUT_MESSAGE = "Enter a Telegram channel as @name or a t.me/name link"
BOARD_INVALID_INPUT_MESSAGE = "Not a Greenhouse, Lever or Teamtailor job board link"

# Telegram usernames: 5-32 letters, digits or underscores.
_TELEGRAM_HANDLE = r"[A-Za-z0-9_]{5,32}"

_TELEGRAM_AT_OR_BARE = re.compile(rf"@?(?P<handle>{_TELEGRAM_HANDLE})")

# t.me links: optional http(s) scheme, exact host `t.me`, optional `/s/`
# preview prefix, the handle, an optional numeric post id, an optional
# trailing slash and an optional simple query (e.g. `?single`).
_TELEGRAM_LINK = re.compile(
    r"(?:https?://)?t\.me/(?:s/)?"
    rf"(?P<handle>{_TELEGRAM_HANDLE})"
    r"(?:/\d{1,12})?/?(?:\?[A-Za-z0-9_=&]{0,64})?",
    # ASCII: without it IGNORECASE lets `[a-z]` match the Kelvin sign and
    # the long s, which would smuggle non-ASCII letters into the handle.
    re.IGNORECASE | re.ASCII,
)


# Board tokens / company slugs: stored lowercased, 1-64 chars (the column size).
_BOARD_HANDLE = r"[A-Za-z0-9_-]{1,64}"
# A simple query string such as `?gh_jid=123` or `?lever-source=x`.
_SIMPLE_QUERY = r"(?:\?[A-Za-z0-9_=&%.+-]{0,150})?"

# Exact hosts only: `(?:https?://)?` then the host, then `/`. With fullmatch
# there is no room for userinfo, ports, other subdomains or look-alikes such
# as `jobs.lever.co.evil.com`.
_GREENHOUSE_LINK = re.compile(
    r"(?:https?://)?(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/"
    rf"(?P<handle>{_BOARD_HANDLE})"
    r"(?:/jobs/\d{1,20})?/?"
    rf"{_SIMPLE_QUERY}",
    re.IGNORECASE | re.ASCII,
)
# Greenhouse paths that are not board tokens.
_GREENHOUSE_RESERVED = frozenset({"embed", "v1", "api"})

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_LEVER_LINK = re.compile(
    r"(?:https?://)?jobs\.(?P<eu>eu\.)?lever\.co/"
    rf"(?P<handle>{_BOARD_HANDLE})"
    rf"(?:/{_UUID}(?:/apply)?)?/?"
    rf"{_SIMPLE_QUERY}",
    re.IGNORECASE | re.ASCII,
)

# `<sub>.teamtailor.com`: one DNS label (no dots, no dash at either end), then
# the exact host, then an optional path and simple query. With fullmatch there
# is no room for userinfo, ports, extra subdomains or `.teamtailor.com.evil.com`.
_TEAMTAILOR_LINK = re.compile(
    r"(?:https?://)?"
    r"(?P<handle>[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)"
    r"\.teamtailor\.com"
    r"(?:/[A-Za-z0-9_.~%/-]{0,500})?"
    rf"{_SIMPLE_QUERY}",
    re.IGNORECASE | re.ASCII,
)
# Teamtailor's own service hosts, not company boards.
_TEAMTAILOR_RESERVED = frozenset({"www", "app", "api"})

_BOARD_HOST_SUFFIXES = (".greenhouse.io", ".lever.co", ".teamtailor.com")
_HAS_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")


class SourceInputError(ValueError):
    """The input is not a recognised channel or board reference."""

    def __init__(self, message: str = INVALID_INPUT_MESSAGE) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True, slots=True)
class ParsedSource:
    kind: str
    handle: str


def _parse_telegram(text: str) -> ParsedSource | None:
    match = _TELEGRAM_AT_OR_BARE.fullmatch(text) or _TELEGRAM_LINK.fullmatch(text)
    if match is None:
        return None
    return ParsedSource(kind="telegram", handle=match["handle"].lower())


def _parse_greenhouse(text: str) -> ParsedSource | None:
    match = _GREENHOUSE_LINK.fullmatch(text)
    if match is None:
        return None
    handle = match["handle"].lower()
    if handle in _GREENHOUSE_RESERVED:
        return None
    return ParsedSource(kind="greenhouse", handle=handle)


def _parse_lever(text: str) -> ParsedSource | None:
    match = _LEVER_LINK.fullmatch(text)
    if match is None:
        return None
    kind = "lever_eu" if match["eu"] else "lever"
    return ParsedSource(kind=kind, handle=match["handle"].lower())


def _parse_teamtailor(text: str) -> ParsedSource | None:
    match = _TEAMTAILOR_LINK.fullmatch(text)
    if match is None:
        return None
    handle = match["handle"].lower()
    if handle in _TEAMTAILOR_RESERVED:
        return None
    return ParsedSource(kind="teamtailor", handle=handle)


_PARSERS: tuple[Callable[[str], ParsedSource | None], ...] = (
    _parse_telegram,
    _parse_greenhouse,
    _parse_lever,
    _parse_teamtailor,
)


def _input_host(text: str) -> str | None:
    """The lowercased host the input names (with or without a scheme), if any."""
    try:
        has_netloc = _HAS_SCHEME.match(text) or text.startswith("//")
        parts = urlsplit(text if has_netloc else f"//{text}")
    except ValueError:
        return None
    return parts.hostname


def _is_board_host(host: str | None) -> bool:
    if not host:
        return False
    return f".{host.rstrip('.')}".endswith(_BOARD_HOST_SUFFIXES)


def _invalid_input_message(text: str) -> str:
    """Pick the hint for unrecognised input (rule in the module docstring)."""
    if _is_board_host(_input_host(text)):
        return BOARD_INVALID_INPUT_MESSAGE
    return INVALID_INPUT_MESSAGE


def parse_source_input(raw: str) -> ParsedSource:
    """Parse user input into a source kind and a lowercased handle.

    Raises:
        SourceInputError: if the input is too long, contains whitespace or
            control characters, or matches no supported pattern. Its message
            is the Telegram or the board hint (see `_invalid_input_message`).
    """
    text = raw.strip()
    if not text:
        raise SourceInputError
    if len(text) > MAX_INPUT_LENGTH or any(
        ch.isspace() or not ch.isprintable() for ch in text
    ):
        raise SourceInputError(_invalid_input_message(text))
    for parser in _PARSERS:
        parsed = parser(text)
        if parsed is not None:
            return parsed
    raise SourceInputError(_invalid_input_message(text))
