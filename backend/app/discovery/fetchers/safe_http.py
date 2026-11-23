"""Guarded HTTP fetcher for user-supplied web page URLs.

A `web` source is any URL a user types in, so every request made for it must
not be steerable into the server's own network (SSRF). The rules:

- ``http``/``https`` only, ports 80/443 only, no ``user:pass@`` part;
- the host is resolved once per hop and the request is rejected if ANY
  address is not globally routable (private, loopback, link-local incl. the
  cloud metadata address, CGNAT, multicast, reserved, NAT64, ...);
- the connection goes to the checked IP literal itself, with the original
  name in the ``Host`` header and as TLS SNI / certificate name, so DNS can't
  give a different answer between the check and the connect (rebinding);
- redirects are followed by hand and every hop is checked again;
- proxies from the environment are ignored, keep-alive is off (a pooled
  connection is keyed by IP and must not be reused for another TLS name);
- no cookies are sent or kept (the jar would be keyed by the pinned IP and
  shared across sites and users); ``Accept-Encoding: identity`` is sent;
- total time, body size (decompressed) and content type are capped.
"""

import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

__all__ = [
    "FetchErrorReason",
    "FetchedPage",
    "PageFetchError",
    "Resolver",
    "UnsafeUrlError",
    "USER_AGENT",
    "check_address",
    "fetch_html",
    "make_client",
    "system_resolver",
]

USER_AGENT = "Mozilla/5.0 (compatible; Jobbi/1.0)"
ACCEPT = "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1"
ACCEPT_ENCODING = "identity"
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_BYTES = 5_000_000
DEFAULT_MAX_REDIRECTS = 5

_DEFAULT_PORTS = {"http": 80, "https": 443}
_ALLOWED_PORTS = frozenset({80, 443})
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_NOT_FOUND_STATUSES = frozenset({404, 410})
_HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
# NAT64 prefixes embed an IPv4 address but report `is_global` True.
_NAT64_NETWORKS = (
    ipaddress.IPv6Network("64:ff9b::/96"),
    ipaddress.IPv6Network("64:ff9b:1::/48"),
)
# Deprecated site-local range; `is_global` reports it True on Python 3.14.
_SITE_LOCAL_V6 = ipaddress.IPv6Network("fec0::/10")
# `<meta charset=...>` / `content="text/html; charset=..."` near the page top.
_META_CHARSET_RE = re.compile(
    rb"""<meta[^>]+charset\s*=\s*["']?([A-Za-z0-9_.:-]+)""", re.I
)
_META_SNIFF_BYTES = 4096

FetchErrorReason = Literal["unreachable", "not_found", "not_html", "too_large"]
Resolver = Callable[[str, int], Awaitable[list[str]]]


class UnsafeUrlError(Exception):
    """The URL may not be fetched (scheme, port, credentials or address).

    The API shows it as "This link can't be used".
    """


class PageFetchError(Exception):
    """A page could not be read.

    ``reason``: ``not_found`` (HTTP 404/410), ``not_html`` (other content
    type), ``too_large`` (body over the cap) or ``unreachable`` (DNS, network,
    timeout, any other HTTP >= 400, too many redirects).
    """

    def __init__(self, reason: FetchErrorReason) -> None:
        super().__init__(reason)
        self.reason: FetchErrorReason = reason


@dataclass(frozen=True, slots=True)
class FetchedPage:
    """A fetched HTML page; ``final_url`` is the URL after redirects."""

    final_url: str
    status: int
    text: str


@dataclass(frozen=True, slots=True)
class _Target:
    scheme: str
    host: str  # ASCII (IDNA) host name or IP literal, lowercase, no brackets
    port: int
    path_query: str  # "/path?query", never empty


def make_client() -> httpx.AsyncClient:
    """The HTTP client to pass to :func:`fetch_html`.

    ``trust_env=False`` so ``HTTP(S)_PROXY`` cannot route around the address
    check; no redirects and no keep-alive (see the module docstring).
    """
    return httpx.AsyncClient(
        trust_env=False,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": ACCEPT},
        limits=httpx.Limits(max_keepalive_connections=0),
    )


async def system_resolver(host: str, port: int) -> list[str]:
    """Resolve ``host`` with the OS resolver (non-blocking)."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def _is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip in _SITE_LOCAL_V6 or any(ip in net for net in _NAT64_NETWORKS):
            return True
        elif ip.sixtofour is not None:
            ip = ip.sixtofour
    # `is_global` alone misses multicast on older Pythons; check explicitly.
    return (
        not ip.is_global
        or ip.is_multicast
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
    )


def check_address(address: str) -> str:
    """Return ``address`` (an IP literal) if it is publicly routable.

    Raises:
        UnsafeUrlError: not an IP address, or not a global one.
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError as exc:
        raise UnsafeUrlError(address) from exc
    if _is_blocked(ip):
        raise UnsafeUrlError(address)
    return ip.compressed


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _parse_target(url: str) -> _Target:
    try:
        parts = urlsplit(url.strip())
        explicit_port = parts.port
    except ValueError as exc:
        raise UnsafeUrlError(url) from exc
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        raise UnsafeUrlError(url)
    if parts.username is not None or parts.password is not None:
        raise UnsafeUrlError(url)
    if explicit_port is not None and explicit_port not in _ALLOWED_PORTS:
        raise UnsafeUrlError(url)
    host = (parts.hostname or "").rstrip(".")
    if not host:
        raise UnsafeUrlError(url)
    if not _is_ip_literal(host):
        try:
            host = host.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise UnsafeUrlError(url) from exc
    path_query = parts.path or "/"
    if parts.query:
        path_query = f"{path_query}?{parts.query}"
    return _Target(
        scheme=scheme,
        host=host,
        port=explicit_port or _DEFAULT_PORTS[scheme],
        path_query=path_query,
    )


async def _pick_address(target: _Target, resolver: Resolver) -> str:
    """The one checked IP to connect to; every resolved address must pass."""
    if _is_ip_literal(target.host):
        return check_address(target.host)
    try:
        addresses = await resolver(target.host, target.port)
    except OSError as exc:  # socket.gaierror is an OSError
        raise PageFetchError("unreachable") from exc
    if not addresses:
        raise PageFetchError("unreachable")
    checked = [check_address(address) for address in addresses]
    return checked[0]


def _pinned_request(
    client: httpx.AsyncClient, target: _Target, ip: str, timeout_s: float
) -> httpx.Request:
    netloc_host = f"[{ip}]" if ":" in ip else ip
    host_header = f"[{target.host}]" if ":" in target.host else target.host
    default_port = _DEFAULT_PORTS[target.scheme]
    port_suffix = "" if target.port == default_port else f":{target.port}"
    path, _, query = target.path_query.partition("?")
    pinned_url = urlunsplit(
        (target.scheme, f"{netloc_host}{port_suffix}", path, query, "")
    )
    extensions: dict[str, object] = {}
    if target.scheme == "https":
        # httpcore passes this as `server_hostname` to the TLS handshake:
        # it is sent as SNI and the certificate is verified against it.
        extensions["sni_hostname"] = target.host
    # The jar is keyed by the pinned IP, so a cookie set by one site would go
    # to every other site (and user) on that IP: never send or keep any.
    client.cookies.clear()
    return client.build_request(
        "GET",
        pinned_url,
        headers={
            "Host": f"{host_header}{port_suffix}",
            "User-Agent": USER_AGENT,
            "Accept": ACCEPT,
            # Plain bodies only: a compressed one could inflate far past the
            # size cap inside a single chunk before it is counted.
            "Accept-Encoding": ACCEPT_ENCODING,
        },
        extensions=extensions,
        timeout=timeout_s,
    )


def _decode(body: bytes, response: httpx.Response) -> str:
    encoding = response.charset_encoding
    if encoding is None:
        match = _META_CHARSET_RE.search(body[:_META_SNIFF_BYTES])
        encoding = match.group(1).decode("ascii") if match else "utf-8"
    try:
        return body.decode(encoding, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


async def _read_capped(response: httpx.Response, max_bytes: int) -> bytes:
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > max_bytes:
        raise PageFetchError("too_large")
    body = bytearray()
    async for chunk in response.aiter_bytes():  # decompressed chunks
        body.extend(chunk)
        if len(body) > max_bytes:
            raise PageFetchError("too_large")
    return bytes(body)


async def _fetch(
    url: str,
    client: httpx.AsyncClient,
    resolver: Resolver,
    timeout_s: float,
    max_bytes: int,
    max_redirects: int,
) -> FetchedPage:
    current = url.strip()
    for hop in range(max_redirects + 1):
        target = _parse_target(current)
        ip = await _pick_address(target, resolver)
        request = _pinned_request(client, target, ip, timeout_s)
        response = await client.send(request, stream=True)
        try:
            status = response.status_code
            if status in _REDIRECT_STATUSES:
                location = response.headers.get("location")
                if not location or hop == max_redirects:
                    raise PageFetchError("unreachable")
                # 301/302/303 become GET; we only ever send GET anyway.
                current = urljoin(current, location.strip())
                continue
            if status in _NOT_FOUND_STATUSES:
                raise PageFetchError("not_found")
            if not 200 <= status < 300:
                raise PageFetchError("unreachable")
            media_type = (
                response.headers.get("content-type", "").split(";")[0].strip().lower()
            )
            if media_type not in _HTML_TYPES:
                raise PageFetchError("not_html")
            body = await _read_capped(response, max_bytes)
            return FetchedPage(
                final_url=current, status=status, text=_decode(body, response)
            )
        finally:
            await response.aclose()
            client.cookies.clear()  # drop whatever this hop set
    raise PageFetchError("unreachable")  # pragma: no cover - loop always exits


async def fetch_html(
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
    resolver: Resolver = system_resolver,
    timeout_s: float = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
) -> FetchedPage:
    """GET an HTML page from a user-supplied URL under the SSRF guard.

    ``client`` must come from :func:`make_client` (or be equally configured);
    when omitted, a client is created for this call.

    Raises:
        UnsafeUrlError: the URL or any redirect hop breaks a guard rule.
        PageFetchError: the page could not be read (see its ``reason``).
        ValueError: ``client`` trusts the environment or follows redirects.
    """
    if client is None:
        async with make_client() as own_client:
            return await fetch_html(
                url,
                client=own_client,
                resolver=resolver,
                timeout_s=timeout_s,
                max_bytes=max_bytes,
                max_redirects=max_redirects,
            )
    if client.trust_env or client.follow_redirects:
        raise ValueError("fetch_html needs a client from make_client()")
    try:
        async with asyncio.timeout(timeout_s):
            return await _fetch(
                url, client, resolver, timeout_s, max_bytes, max_redirects
            )
    except TimeoutError as exc:
        raise PageFetchError("unreachable") from exc
    except httpx.InvalidURL as exc:  # e.g. control characters in the path
        raise UnsafeUrlError(url) from exc
    except httpx.HTTPError as exc:
        raise PageFetchError("unreachable") from exc
