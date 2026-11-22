"""Turn what the user typed into a (kind, handle) pair.

The user's text is never fetched. It is only matched against strict, anchored
patterns; the handle extracted here is later combined with a fixed host
(`https://t.me/s/<handle>`), so look-alike hosts or odd paths cannot steer a
request anywhere else (no SSRF).

Slice 6 adds Greenhouse / Lever board parsers: append a function to
`_PARSERS` that returns a `ParsedSource` or None.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

MAX_INPUT_LENGTH = 200

INVALID_INPUT_MESSAGE = "Enter a Telegram channel as @name or a t.me/name link"

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


_PARSERS: tuple[Callable[[str], ParsedSource | None], ...] = (_parse_telegram,)


def parse_source_input(raw: str) -> ParsedSource:
    """Parse user input into a source kind and a lowercased handle.

    Raises:
        SourceInputError: if the input is too long, contains whitespace or
            control characters, or matches no supported pattern.
    """
    text = raw.strip()
    if not text or len(text) > MAX_INPUT_LENGTH:
        raise SourceInputError
    if any(ch.isspace() or not ch.isprintable() for ch in text):
        raise SourceInputError
    for parser in _PARSERS:
        parsed = parser(text)
        if parsed is not None:
            return parsed
    raise SourceInputError
