"""URL normalization shared by job-link extraction and duplicate detection."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

__all__ = ["is_http_url", "normalize_url"]

_DEFAULT_PORTS = {"http": 80, "https": 443}


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
