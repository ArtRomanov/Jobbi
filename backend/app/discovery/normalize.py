"""URL normalization shared by job-link extraction and duplicate detection,
and the cleaner for remote titles and texts."""

import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

__all__ = ["is_http_url", "normalize_url", "strip_invisible"]

_DEFAULT_PORTS = {"http": 80, "https": 443}
# Cc = control (NUL breaks PostgreSQL text), Cf = format (zero-width, BOM,
# bidi, tag characters), Cs = lone surrogates (not encodable as UTF-8: a
# JSON response or a DB insert would fail). Whitespace is always kept.
_TITLE_DROP = frozenset({"Cc", "Cf", "Cs"})
_TEXT_DROP = frozenset({"Cc", "Cs"})
_KEPT_CONTROLS = frozenset("\t\n\r")


def strip_invisible(value: str, *, keep_format: bool = False) -> str:
    """Remove control, format and surrogate characters from remote text.

    Tab, newline and carriage return are kept (other controls, including the
    C1 range and NEL, are not); space characters (``Zs``) are never touched.
    With ``keep_format`` (body text) format characters stay, so emoji
    sequences joined by U+200D are not broken; lone surrogates and controls
    still go. The result always encodes as UTF-8. Linear in the length of
    ``value``.
    """
    drop = _TEXT_DROP if keep_format else _TITLE_DROP
    return "".join(
        ch
        for ch in value
        if ch in _KEPT_CONTROLS or unicodedata.category(ch) not in drop
    )


def is_http_url(url: str) -> bool:
    """True if `url` is an absolute http(s) URL with a host (scheme case-insensitive).

    Rejects `javascript:`, `data:`, relative and malformed URLs, so a link from a
    remote board can never become a script or data link in the UI.
    """
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return False
    return parts.scheme.lower() in _DEFAULT_PORTS and bool(parts.hostname)


def normalize_url(url: str) -> str:
    """Return a canonical form of `url` so that equal links compare equal.

    - scheme and host are lowercased; user info and default ports are dropped;
    - the fragment and every `utm_*` query parameter are removed (other parameters
      keep their order);
    - a trailing slash on the path is removed.

    Input without a scheme or host is returned stripped but otherwise unchanged.
    """
    raw = url.strip()
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        return raw
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if not scheme or not host:
        return raw

    netloc = host if ":" not in host else f"[{host}]"
    if port is not None and _DEFAULT_PORTS.get(scheme) != port:
        netloc = f"{netloc}:{port}"

    path = parts.path.rstrip("/")
    query_pairs = [
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if not name.lower().startswith("utm_")
    ]
    query = urlencode(query_pairs)
    return urlunsplit((scheme, netloc, path, query, ""))
