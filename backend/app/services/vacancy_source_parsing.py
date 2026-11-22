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

Which error text an unrecognised input gets (`_invalid_input_message`):
- it mentions `greenhouse.io` or `lever.co`, or it is an http(s) URL whose
  host does not look like Telegram -> BOARD_INVALID_INPUT_MESSAGE;
- anything else (`@name`, bare words, t.me look-alikes) ->
  INVALID_INPUT_MESSAGE (the Telegram hint).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

MAX_INPUT_LENGTH = 200

INVALID_INPUT_MESSAGE = "Enter a Telegram channel as @name or a t.me/name link"
BOARD_INVALID_INPUT_MESSAGE = "Not a Greenhouse or Lever job board link"

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

_BOARD_DOMAIN_HINT = re.compile(r"greenhouse\.io|lever\.co", re.IGNORECASE)
_HTTP_URL = re.compile(r"https?://(?P<host>[^/?#]*)", re.IGNORECASE)
_TELEGRAM_HOST_HINT = re.compile(r"t\.me|telegram", re.IGNORECASE)


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


_PARSERS: tuple[Callable[[str], ParsedSource | None], ...] = (
    _parse_telegram,
    _parse_greenhouse,
    _parse_lever,
)


def _invalid_input_message(text: str) -> str:
    """Pick the hint for unrecognised input (rule in the module docstring)."""
    if _BOARD_DOMAIN_HINT.search(text):
        return BOARD_INVALID_INPUT_MESSAGE
    url = _HTTP_URL.match(text)
    if url is not None and not _TELEGRAM_HOST_HINT.search(url["host"]):
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
