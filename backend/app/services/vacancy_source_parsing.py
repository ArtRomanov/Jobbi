"""Turn what the user typed into a (kind, handle) pair, or a web page URL.

Telegram and board inputs are only matched against strict, anchored patterns;
the handle extracted here is later combined with a fixed host
(`https://t.me/s/<handle>`), so look-alike hosts or odd paths cannot steer a
request anywhere else (no SSRF). Any other http(s) link becomes a `web`
source: its URL is fetched only through `discovery/fetchers/safe_http.py`,
which enforces the address and port rules (this module checks only scheme,
credentials and the shape of the host).

Supported inputs:
- Telegram: `@name`, `name`, `t.me/name`, `t.me/s/name` -> kind `telegram`.
- Greenhouse: `boards.greenhouse.io/<token>`, `job-boards.greenhouse.io/<token>`
  and their `.eu.` variants -> kind `greenhouse` (EU tokens are served by the
  standard API host, so the region is not stored).
- Lever: `jobs.lever.co/<company>` -> `lever`, `jobs.eu.lever.co/<company>` ->
  `lever_eu` (Lever keeps a company's data in one region).
- Teamtailor: `<sub>.teamtailor.com[/any path]` -> `teamtailor`, handle `<sub>`;
  only `https://<sub>.teamtailor.com/jobs.rss` is ever requested.
- Web page: any other `http(s)://host/...` link, or `host.tld/...` without a
  scheme (https is assumed) -> `web`, with the normalized URL in `url` and an
  empty handle (the source id becomes the handle when it is saved).

Order: Telegram -> Greenhouse/Lever -> Teamtailor -> web. Error texts:
- a scheme other than http/https (`file:`, `ftp:`, `javascript:`, ...), a
  `user:pass@` part, an invalid port or an over-long link -> UNSAFE_LINK_MESSAGE;
- the parsed host is, or ends with, `.greenhouse.io`, `.lever.co` or
  `.teamtailor.com` but no board pattern matched -> BOARD_INVALID_INPUT_MESSAGE
  (a host check, not a substring search, so `clever.com/careers` is a web page);
- the host is Telegram's (`t.me`, `telegram.me`) but no channel pattern matched,
  or the input is neither a channel name nor a link -> INVALID_INPUT_MESSAGE
  (the Telegram hint).
"""

import ipaddress
import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.discovery.normalize import normalize_url

# Web page links may be long (search filters live in the query string); the
# column is String(2048). Telegram and board patterns only run on inputs up to
# MAX_HANDLE_INPUT_LENGTH, which also bounds their regex work.
MAX_INPUT_LENGTH = 2048
MAX_HANDLE_INPUT_LENGTH = 200

INVALID_INPUT_MESSAGE = "Enter a Telegram channel as @name or a t.me/name link"
BOARD_INVALID_INPUT_MESSAGE = "Not a Greenhouse, Lever or Teamtailor job board link"
UNSAFE_LINK_MESSAGE = "This link can't be used"

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
_TELEGRAM_HOST_SUFFIXES = (".t.me", ".telegram.me")
_HAS_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")
# `scheme:` at the start. `host.tld:8080` matches too; `_url_scheme` tells
# the two apart by what follows the colon (a port number).
_SCHEME_PREFIX = re.compile(
    r"(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*):(?P<rest>.*)", re.DOTALL
)
_HTTP_SCHEMES = frozenset({"http", "https"})
_HOST_LABEL = re.compile(r"(?!-)[a-z0-9-]{1,63}(?<!-)")


class SourceInputError(ValueError):
    """The input is not a recognised channel, board or web page link."""

    def __init__(self, message: str = INVALID_INPUT_MESSAGE) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True, slots=True)
class ParsedSource:
    kind: str
    # Lowercased channel / board handle; empty for `web` until it is saved.
    handle: str
    # `web` only: the normalized listing URL.
    url: str | None = None


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


def _host_has_suffix(host: str | None, suffixes: tuple[str, ...]) -> bool:
    if not host:
        return False
    return f".{host.rstrip('.')}".endswith(suffixes)


def _is_board_host(host: str | None) -> bool:
    return _host_has_suffix(host, _BOARD_HOST_SUFFIXES)


def _is_telegram_host(host: str | None) -> bool:
    return _host_has_suffix(host, _TELEGRAM_HOST_SUFFIXES)


def _url_scheme(text: str) -> str | None:
    """The input's scheme, lowercased; None when it has none.

    `host.tld:8080/x` is a host with a port, not the scheme `host.tld`.
    """
    match = _SCHEME_PREFIX.match(text)
    if match is None:
        return None
    rest = match["rest"]
    if rest[:1].isdigit():
        return None
    return match["scheme"].lower()


def _is_valid_host(host: str) -> bool:
    """An IP literal, `localhost`, or a dotted DNS name (IDN allowed).

    Whether the address may be fetched is decided later by `safe_http`.
    """
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return True
    host = host.rstrip(".")
    if host == "localhost":
        return True
    try:
        ascii_host = host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return False
    labels = ascii_host.split(".")
    if len(labels) < 2 or not any(ch.isalpha() for ch in labels[-1]):
        return False
    return all(_HOST_LABEL.fullmatch(label) for label in labels)


def _invalid_input_message(text: str) -> str:
    """Pick the error text for input that is not usable as it is."""
    if _is_board_host(_input_host(text)):
        return BOARD_INVALID_INPUT_MESSAGE
    if _url_scheme(text) is not None:
        return UNSAFE_LINK_MESSAGE
    return INVALID_INPUT_MESSAGE


def _parse_web(text: str) -> ParsedSource:
    """Turn an http(s) link (scheme optional) into a `web` source.

    Raises:
        SourceInputError: a non-http scheme, not a link, a Telegram or board
            host that did not match its pattern, credentials in the link, an
            invalid port, or a normalized URL longer than MAX_INPUT_LENGTH.
    """
    scheme = _url_scheme(text)
    if scheme is not None and scheme not in _HTTP_SCHEMES:
        raise SourceInputError(UNSAFE_LINK_MESSAGE)
    if scheme is None:
        text = f"https:{text}" if text.startswith("//") else f"https://{text}"
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError as exc:
        raise SourceInputError(UNSAFE_LINK_MESSAGE) from exc
    host = parts.hostname
    if _is_board_host(host):
        raise SourceInputError(BOARD_INVALID_INPUT_MESSAGE)
    if _is_telegram_host(host):
        raise SourceInputError(INVALID_INPUT_MESSAGE)
    if not host or not _is_valid_host(host):
        # Without a scheme it was probably a mistyped channel name.
        raise SourceInputError(
            INVALID_INPUT_MESSAGE if scheme is None else UNSAFE_LINK_MESSAGE
        )
    if parts.username is not None or parts.password is not None or port == 0:
        raise SourceInputError(UNSAFE_LINK_MESSAGE)
    url = normalize_url(text)
    if len(url) > MAX_INPUT_LENGTH:
        raise SourceInputError(UNSAFE_LINK_MESSAGE)
    return ParsedSource(kind="web", handle="", url=url)


def parse_source_input(raw: str) -> ParsedSource:
    """Parse user input into a source kind and a lowercased handle (or a URL).

    Raises:
        SourceInputError: the input is empty, too long, contains whitespace or
            control characters, or matches no supported form. Its message is
            one of the texts listed in the module docstring.
    """
    text = raw.strip()
    if not text:
        raise SourceInputError
    if len(text) > MAX_INPUT_LENGTH or any(
        ch.isspace() or not ch.isprintable() for ch in text
    ):
        raise SourceInputError(_invalid_input_message(text))
    if len(text) <= MAX_HANDLE_INPUT_LENGTH:
        for parser in _PARSERS:
            parsed = parser(text)
            if parsed is not None:
                return parsed
    return _parse_web(text)
