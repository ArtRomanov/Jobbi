"""Tests for the SSRF-guarded HTML fetcher."""

import asyncio
import datetime as dt
import gzip
import ssl
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterator
from pathlib import Path

import httpx
import pytest
import respx

from app.discovery.fetchers import safe_http
from app.discovery.fetchers.safe_http import (
    USER_AGENT,
    FetchedPage,
    PageFetchError,
    UnsafeUrlError,
    check_address,
    fetch_html,
    make_client,
)

PUBLIC_IP = "93.184.216.34"
OTHER_PUBLIC_IP = "151.101.1.69"
PUBLIC_IP6 = "2606:2800:220:1:248:1893:25c8:1946"
HTML = {"content-type": "text/html; charset=utf-8"}


def resolver_for(
    table: dict[str, list[str]], calls: list[str] | None = None
) -> Callable[[str, int], Awaitable[list[str]]]:
    async def _resolve(host: str, port: int) -> list[str]:
        if calls is not None:
            calls.append(host)
        return table[host]

    return _resolve


PUBLIC = resolver_for(
    {"jobs.example.com": [PUBLIC_IP], "cdn.example.net": [OTHER_PUBLIC_IP]}
)


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with make_client() as http_client:
        yield http_client


# --- address rules ------------------------------------------------------------


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",  # cloud metadata
        "100.64.0.1",  # CGNAT
        "0.0.0.0",
        "224.0.0.1",  # multicast
        "240.0.0.1",  # reserved
        "255.255.255.255",
        "::1",
        "::",
        "fe80::1",
        "fc00::1",
        "ff02::1",
        "::ffff:127.0.0.1",  # IPv4-mapped loopback
        "::ffff:10.0.0.1",
        "64:ff9b::7f00:1",  # NAT64 of 127.0.0.1
        "64:ff9b::808:808",  # NAT64 is blocked even for a public IPv4
        "64:ff9b:1::1",  # local-use NAT64
        "2002:7f00:1::",  # 6to4 wrapping 127.0.0.1
        "not-an-ip",
    ],
)
def test_check_address_blocks_non_global(address: str) -> None:
    with pytest.raises(UnsafeUrlError):
        check_address(address)


@pytest.mark.parametrize(
    "address", [PUBLIC_IP, "8.8.8.8", PUBLIC_IP6, "::ffff:8.8.8.8"]
)
def test_check_address_allows_global(address: str) -> None:
    assert check_address(address)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/jobs",
        "http://0.0.0.0/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "https://[64:ff9b::7f00:1]/",
        "http://[fe80::1%25en0]/",
    ],
)
async def test_ip_literal_urls_are_checked(url: str, client: httpx.AsyncClient) -> None:
    calls: list[str] = []
    with respx.mock(assert_all_called=False) as router:
        catch_all = router.route().respond(200, headers=HTML, text="x")
        with pytest.raises(UnsafeUrlError):
            await fetch_html(url, client=client, resolver=resolver_for({}, calls))
    assert not catch_all.called
    assert calls == []


@pytest.mark.parametrize(
    "resolved",
    [
        ["127.0.0.1"],
        ["10.0.0.7"],
        ["169.254.169.254"],
        ["::ffff:127.0.0.1"],
        ["64:ff9b::7f00:1"],
        [PUBLIC_IP, "192.168.0.10"],  # ANY bad address rejects the host
        ["::1", PUBLIC_IP],
    ],
)
async def test_host_resolving_to_non_global_is_rejected(
    resolved: list[str], client: httpx.AsyncClient
) -> None:
    with respx.mock(assert_all_called=False) as router:
        catch_all = router.route().respond(200, headers=HTML, text="x")
        with pytest.raises(UnsafeUrlError):
            await fetch_html(
                "https://jobs.example.com/",
                client=client,
                resolver=resolver_for({"jobs.example.com": resolved}),
            )
    assert not catch_all.called


@pytest.mark.parametrize(
    "url",
    [
        "ftp://jobs.example.com/",
        "file:///etc/passwd",
        "gopher://jobs.example.com/",
        "javascript:alert(1)",
        "jobs.example.com/careers",
        "https://jobs.example.com:8443/",
        "http://jobs.example.com:22/",
        "http://jobs.example.com:0/",
        "http://jobs.example.com:99999/",
        "https://user:pass@jobs.example.com/",
        "https://user@jobs.example.com/",
        "https:///nohost",
        "https://jobs.example.com/a\x00b",
    ],
)
async def test_bad_scheme_port_or_userinfo_is_rejected(
    url: str, client: httpx.AsyncClient
) -> None:
    with pytest.raises(UnsafeUrlError):
        await fetch_html(url, client=client, resolver=PUBLIC)


@respx.mock
async def test_explicit_default_ports_are_allowed(client: httpx.AsyncClient) -> None:
    respx.get(f"https://{PUBLIC_IP}/a").respond(200, headers=HTML, text="ok")
    respx.get(f"http://{PUBLIC_IP}/b").respond(200, headers=HTML, text="ok")

    assert (
        await fetch_html(
            "https://jobs.example.com:443/a", client=client, resolver=PUBLIC
        )
    ).text == "ok"
    assert (
        await fetch_html("http://jobs.example.com:80/b", client=client, resolver=PUBLIC)
    ).text == "ok"


# --- IP pinning -------------------------------------------------------------------


@respx.mock
async def test_request_goes_to_checked_ip_with_host_header_and_sni(
    client: httpx.AsyncClient,
) -> None:
    route = respx.get(f"https://{PUBLIC_IP}/careers?page=2").respond(
        200, headers=HTML, text="<html>hi</html>"
    )

    page = await fetch_html(
        "https://Jobs.Example.com/careers?page=2", client=client, resolver=PUBLIC
    )

    assert page == FetchedPage(
        final_url="https://Jobs.Example.com/careers?page=2",
        status=200,
        text="<html>hi</html>",
    )
    request = route.calls.last.request
    assert request.url.host == PUBLIC_IP
    assert request.headers["host"] == "jobs.example.com"
    assert request.headers["user-agent"] == USER_AGENT
    assert "text/html" in request.headers["accept"]
    assert request.extensions["sni_hostname"] == "jobs.example.com"


@respx.mock
async def test_ipv6_address_is_bracketed_and_http_has_no_sni(
    client: httpx.AsyncClient,
) -> None:
    route = respx.get(f"http://[{PUBLIC_IP6}]/").respond(200, headers=HTML, text="ok")

    await fetch_html(
        "http://jobs.example.com",
        client=client,
        resolver=resolver_for({"jobs.example.com": [PUBLIC_IP6]}),
    )

    request = route.calls.last.request
    assert request.url.host == PUBLIC_IP6
    assert request.headers["host"] == "jobs.example.com"
    assert "sni_hostname" not in request.extensions


@respx.mock
async def test_public_ip_literal_url_is_fetched_without_dns(
    client: httpx.AsyncClient,
) -> None:
    calls: list[str] = []
    route = respx.get(f"http://{PUBLIC_IP}/").respond(200, headers=HTML, text="ok")

    await fetch_html(
        f"http://{PUBLIC_IP}/", client=client, resolver=resolver_for({}, calls)
    )

    assert calls == []
    assert route.calls.last.request.headers["host"] == PUBLIC_IP


@respx.mock
async def test_dns_rebinding_cannot_swap_the_address(client: httpx.AsyncClient) -> None:
    """The resolver answers public first, private later: only one lookup per
    hop happens and the request goes to the address that was checked."""
    answers = iter([[PUBLIC_IP], ["127.0.0.1"]])
    calls: list[str] = []

    async def rebinding(host: str, port: int) -> list[str]:
        calls.append(host)
        return next(answers)

    route = respx.get(f"https://{PUBLIC_IP}/").respond(200, headers=HTML, text="ok")
    loopback = respx.route(host="127.0.0.1").respond(200, headers=HTML, text="pwned")

    page = await fetch_html(
        "https://jobs.example.com/", client=client, resolver=rebinding
    )

    assert page.text == "ok"
    assert calls == ["jobs.example.com"]
    assert route.call_count == 1
    assert not loopback.called


async def test_dns_failure_is_unreachable(client: httpx.AsyncClient) -> None:
    async def failing(host: str, port: int) -> list[str]:
        raise OSError("Name or service not known")

    with pytest.raises(PageFetchError) as exc_info:
        await fetch_html("https://jobs.example.com/", client=client, resolver=failing)
    assert exc_info.value.reason == "unreachable"


async def test_empty_dns_answer_is_unreachable(client: httpx.AsyncClient) -> None:
    with pytest.raises(PageFetchError) as exc_info:
        await fetch_html(
            "https://jobs.example.com/",
            client=client,
            resolver=resolver_for({"jobs.example.com": []}),
        )
    assert exc_info.value.reason == "unreachable"


async def test_system_resolver_resolves_localhost() -> None:
    addresses = await safe_http.system_resolver("localhost", 80)

    assert addresses
    with pytest.raises(UnsafeUrlError):
        for address in addresses:
            check_address(address)


# --- proxies / client config ------------------------------------------------------


async def test_proxy_environment_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.setenv(name, "http://proxy.invalid:3128")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)

    # Control: a default client would route through the proxy.
    async with httpx.AsyncClient() as default_client:
        assert default_client._mounts

    async with make_client() as guarded:
        target = httpx.URL(f"https://{PUBLIC_IP}/")
        assert guarded._transport_for_url(target) is guarded._transport
        with respx.mock(assert_all_called=False) as router:
            proxy = router.route(host="proxy.invalid").respond(
                200, headers=HTML, text="proxy"
            )
            route = router.get(f"https://{PUBLIC_IP}/").respond(
                200, headers=HTML, text="direct"
            )
            page = await fetch_html(
                "https://jobs.example.com/", client=guarded, resolver=PUBLIC
            )

    assert page.text == "direct"
    assert route.called
    assert not proxy.called


@pytest.mark.parametrize(
    "kwargs", [{"trust_env": True}, {"trust_env": False, "follow_redirects": True}]
)
async def test_misconfigured_client_is_refused(kwargs: dict[str, bool]) -> None:
    async with httpx.AsyncClient(**kwargs) as unsafe_client:
        with pytest.raises(ValueError):
            await fetch_html(
                "https://jobs.example.com/", client=unsafe_client, resolver=PUBLIC
            )


def test_make_client_settings() -> None:
    client = make_client()
    assert client.trust_env is False
    assert client.follow_redirects is False
    assert client.headers["user-agent"] == USER_AGENT


@respx.mock
async def test_without_client_a_guarded_one_is_created() -> None:
    respx.get(f"https://{PUBLIC_IP}/").respond(200, headers=HTML, text="ok")

    page = await fetch_html("https://jobs.example.com/", resolver=PUBLIC)

    assert page.text == "ok"


# --- redirects ----------------------------------------------------------------------


@respx.mock
async def test_relative_redirect_is_followed_and_rechecked(
    client: httpx.AsyncClient,
) -> None:
    calls: list[str] = []
    respx.get(f"https://{PUBLIC_IP}/old").respond(
        301, headers={"location": "../new/list?x=1"}
    )
    final = respx.get(f"https://{PUBLIC_IP}/new/list?x=1").respond(
        200, headers=HTML, text="ok"
    )

    page = await fetch_html(
        "https://jobs.example.com/old",
        client=client,
        resolver=resolver_for({"jobs.example.com": [PUBLIC_IP]}, calls),
    )

    assert page.final_url == "https://jobs.example.com/new/list?x=1"
    assert final.called
    assert calls == ["jobs.example.com", "jobs.example.com"]  # one lookup per hop


@respx.mock
async def test_redirect_to_other_public_host_uses_its_own_ip(
    client: httpx.AsyncClient,
) -> None:
    respx.get(f"https://{PUBLIC_IP}/").respond(
        302, headers={"location": "https://cdn.example.net/jobs"}
    )
    second = respx.get(f"https://{OTHER_PUBLIC_IP}/jobs").respond(
        200, headers=HTML, text="ok"
    )

    page = await fetch_html("https://jobs.example.com/", client=client, resolver=PUBLIC)

    assert page.final_url == "https://cdn.example.net/jobs"
    request = second.calls.last.request
    assert request.headers["host"] == "cdn.example.net"
    assert request.extensions["sni_hostname"] == "cdn.example.net"


@pytest.mark.parametrize(
    "location",
    [
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://internal.corp/",
        "//internal.corp/x",
        "https://jobs.example.com:8080/",
        "file:///etc/passwd",
    ],
)
async def test_redirect_to_unsafe_target_is_rejected(
    location: str, client: httpx.AsyncClient
) -> None:
    resolver = resolver_for(
        {"jobs.example.com": [PUBLIC_IP], "internal.corp": ["10.0.0.1"]}
    )
    with respx.mock(assert_all_called=False) as router:
        router.get(f"https://{PUBLIC_IP}/").respond(302, headers={"location": location})
        other = router.route().respond(200, headers=HTML, text="secret")
        with pytest.raises(UnsafeUrlError):
            await fetch_html(
                "https://jobs.example.com/", client=client, resolver=resolver
            )
    assert not other.called


@respx.mock
async def test_redirect_loop_stops_at_the_limit(client: httpx.AsyncClient) -> None:
    route = respx.get(f"https://{PUBLIC_IP}/loop").respond(
        301, headers={"location": "/loop"}
    )

    with pytest.raises(PageFetchError) as exc_info:
        await fetch_html(
            "https://jobs.example.com/loop", client=client, resolver=PUBLIC
        )

    assert exc_info.value.reason == "unreachable"
    assert route.call_count == 6  # the first request + 5 redirects


@respx.mock
async def test_exactly_max_redirects_is_fine(client: httpx.AsyncClient) -> None:
    for hop in range(3):
        respx.get(f"https://{PUBLIC_IP}/{hop}").respond(
            302, headers={"location": f"/{hop + 1}"}
        )
    respx.get(f"https://{PUBLIC_IP}/3").respond(200, headers=HTML, text="ok")

    page = await fetch_html(
        "https://jobs.example.com/0", client=client, resolver=PUBLIC, max_redirects=3
    )

    assert page.final_url == "https://jobs.example.com/3"


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@respx.mock
async def test_redirects_are_followed_with_get(
    status: int, client: httpx.AsyncClient
) -> None:
    respx.get(f"https://{PUBLIC_IP}/a").respond(status, headers={"location": "/b"})
    final = respx.get(f"https://{PUBLIC_IP}/b").respond(200, headers=HTML, text="ok")

    await fetch_html("https://jobs.example.com/a", client=client, resolver=PUBLIC)

    assert final.calls.last.request.method == "GET"


@respx.mock
async def test_redirect_without_location_is_unreachable(
    client: httpx.AsyncClient,
) -> None:
    respx.get(f"https://{PUBLIC_IP}/").respond(302)

    with pytest.raises(PageFetchError) as exc_info:
        await fetch_html("https://jobs.example.com/", client=client, resolver=PUBLIC)
    assert exc_info.value.reason == "unreachable"


# --- statuses, content type, size, time ------------------------------------------


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (404, "not_found"),
        (410, "not_found"),
        (403, "unreachable"),
        (429, "unreachable"),
        (500, "unreachable"),
        (503, "unreachable"),
        (304, "unreachable"),
    ],
)
@respx.mock
async def test_error_statuses(
    status: int, reason: str, client: httpx.AsyncClient
) -> None:
    respx.get(f"https://{PUBLIC_IP}/").respond(status, headers=HTML, text="nope")

    with pytest.raises(PageFetchError) as exc_info:
        await fetch_html("https://jobs.example.com/", client=client, resolver=PUBLIC)
    assert exc_info.value.reason == reason


@pytest.mark.parametrize(
    "content_type",
    ["application/json", "text/plain", "application/pdf", "image/png", ""],
)
@respx.mock
async def test_non_html_content_is_rejected(
    content_type: str, client: httpx.AsyncClient
) -> None:
    headers = {"content-type": content_type} if content_type else {}
    respx.get(f"https://{PUBLIC_IP}/").respond(200, headers=headers, content=b"{}")

    with pytest.raises(PageFetchError) as exc_info:
        await fetch_html("https://jobs.example.com/", client=client, resolver=PUBLIC)
    assert exc_info.value.reason == "not_html"


@respx.mock
async def test_xhtml_is_accepted(client: httpx.AsyncClient) -> None:
    respx.get(f"https://{PUBLIC_IP}/").respond(
        200, headers={"content-type": "Application/XHTML+XML"}, text="<html/>"
    )

    assert (
        await fetch_html("https://jobs.example.com/", client=client, resolver=PUBLIC)
    ).text == "<html/>"


@respx.mock
async def test_body_over_cap_is_too_large(client: httpx.AsyncClient) -> None:
    respx.get(f"https://{PUBLIC_IP}/").respond(200, headers=HTML, content=b"a" * 2_000)

    with pytest.raises(PageFetchError) as exc_info:
        await fetch_html(
            "https://jobs.example.com/", client=client, resolver=PUBLIC, max_bytes=1_000
        )
    assert exc_info.value.reason == "too_large"


@respx.mock
async def test_cap_counts_decompressed_bytes(client: httpx.AsyncClient) -> None:
    bomb = gzip.compress(b"a" * 100_000)
    assert len(bomb) < 1_000
    respx.get(f"https://{PUBLIC_IP}/").respond(
        200, headers={**HTML, "content-encoding": "gzip"}, content=bomb
    )

    with pytest.raises(PageFetchError) as exc_info:
        await fetch_html(
            "https://jobs.example.com/",
            client=client,
            resolver=PUBLIC,
            max_bytes=10_000,
        )
    assert exc_info.value.reason == "too_large"


@respx.mock
async def test_body_at_cap_is_fine(client: httpx.AsyncClient) -> None:
    respx.get(f"https://{PUBLIC_IP}/").respond(200, headers=HTML, content=b"a" * 1_000)

    page = await fetch_html(
        "https://jobs.example.com/", client=client, resolver=PUBLIC, max_bytes=1_000
    )
    assert len(page.text) == 1_000


@respx.mock
async def test_transport_error_is_unreachable(client: httpx.AsyncClient) -> None:
    respx.get(f"https://{PUBLIC_IP}/").mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(PageFetchError) as exc_info:
        await fetch_html("https://jobs.example.com/", client=client, resolver=PUBLIC)
    assert exc_info.value.reason == "unreachable"


@respx.mock
async def test_total_time_is_capped(client: httpx.AsyncClient) -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, headers=HTML, text="late")

    respx.get(f"https://{PUBLIC_IP}/").mock(side_effect=slow)

    with pytest.raises(PageFetchError) as exc_info:
        await fetch_html(
            "https://jobs.example.com/", client=client, resolver=PUBLIC, timeout_s=0.05
        )
    assert exc_info.value.reason == "unreachable"


async def test_slow_resolver_counts_toward_total_time(
    client: httpx.AsyncClient,
) -> None:
    async def slow(host: str, port: int) -> list[str]:
        await asyncio.sleep(5)
        return [PUBLIC_IP]

    with pytest.raises(PageFetchError) as exc_info:
        await fetch_html(
            "https://jobs.example.com/", client=client, resolver=slow, timeout_s=0.05
        )
    assert exc_info.value.reason == "unreachable"


# --- decoding -------------------------------------------------------------------------


@respx.mock
async def test_decodes_with_header_charset(client: httpx.AsyncClient) -> None:
    respx.get(f"https://{PUBLIC_IP}/").respond(
        200,
        headers={"content-type": "text/html; charset=windows-1251"},
        content="Вакансии".encode("cp1251"),
    )

    page = await fetch_html("https://jobs.example.com/", client=client, resolver=PUBLIC)
    assert page.text == "Вакансии"


@respx.mock
async def test_decodes_with_meta_charset_when_header_has_none(
    client: httpx.AsyncClient,
) -> None:
    body = '<html><head><meta charset="windows-1251"></head>Вакансии</html>'
    respx.get(f"https://{PUBLIC_IP}/").respond(
        200, headers={"content-type": "text/html"}, content=body.encode("cp1251")
    )

    page = await fetch_html("https://jobs.example.com/", client=client, resolver=PUBLIC)
    assert "Вакансии" in page.text


@respx.mock
async def test_invalid_bytes_and_unknown_charset_fall_back_to_utf8(
    client: httpx.AsyncClient,
) -> None:
    respx.get(f"https://{PUBLIC_IP}/").respond(
        200, headers={"content-type": "text/html; charset=x-bogus"}, content=b"ok \xff"
    )

    page = await fetch_html("https://jobs.example.com/", client=client, resolver=PUBLIC)
    assert page.text == "ok �"


# --- real TLS: SNI and certificate verification use the original host name ----------


def _make_cert(host: str) -> tuple[bytes, bytes, bytes]:
    """(ca_pem, cert_pem, key_pem): a CA and a leaf certificate for ``host``."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    now = dt.datetime.now(dt.timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)]))
        .issuer_name(ca_name)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    pem = serialization.Encoding.PEM
    key_pem = leaf_key.private_bytes(
        pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return ca_cert.public_bytes(pem), leaf_cert.public_bytes(pem), key_pem


@pytest.fixture
def tls_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[[str], Awaitable[tuple[int, list[str | None], ssl.SSLContext]]]]:
    """Start a local HTTPS server whose certificate names ``cert_host``.

    The guard is relaxed only for this test (loopback address and a random
    port are otherwise rejected) so the real TLS handshake can run.
    """
    pytest.importorskip("cryptography")
    monkeypatch.setattr(safe_http, "_is_blocked", lambda ip: False)
    servers: list[asyncio.Server] = []

    async def _start(cert_host: str) -> tuple[int, list[str | None], ssl.SSLContext]:
        ca_pem, cert_pem, key_pem = _make_cert(cert_host)
        (tmp_path / "cert.pem").write_bytes(cert_pem)
        (tmp_path / "key.pem").write_bytes(key_pem)
        server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx.load_cert_chain(tmp_path / "cert.pem", tmp_path / "key.pem")
        seen_sni: list[str | None] = []
        server_ctx.sni_callback = lambda sock, name, ctx: seen_sni.append(name)

        async def handle(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            try:
                await reader.readuntil(b"\r\n\r\n")
                body = b"<html>tls ok</html>"
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                    b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                    b"Connection: close\r\n\r\n" + body
                )
                await writer.drain()
            except (ConnectionError, asyncio.IncompleteReadError, ssl.SSLError):
                pass
            finally:
                writer.close()

        server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=server_ctx)
        servers.append(server)
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr(safe_http, "_ALLOWED_PORTS", frozenset({80, 443, port}))
        client_ctx = ssl.create_default_context(cadata=ca_pem.decode())
        return port, seen_sni, client_ctx

    yield _start
    for server in servers:
        server.close()


async def test_tls_sni_and_certificate_use_the_original_host(
    tls_server: Callable[
        [str], Awaitable[tuple[int, list[str | None], ssl.SSLContext]]
    ],
) -> None:
    port, seen_sni, client_ctx = await tls_server("jobs.example.test")
    async with httpx.AsyncClient(
        verify=client_ctx, trust_env=False, follow_redirects=False
    ) as tls_client:
        page = await fetch_html(
            f"https://jobs.example.test:{port}/",
            client=tls_client,
            resolver=resolver_for({"jobs.example.test": ["127.0.0.1"]}),
        )

    assert page.text == "<html>tls ok</html>"
    assert seen_sni == ["jobs.example.test"]


async def test_tls_certificate_for_another_name_is_refused(
    tls_server: Callable[
        [str], Awaitable[tuple[int, list[str | None], ssl.SSLContext]]
    ],
) -> None:
    port, seen_sni, client_ctx = await tls_server("other.example.test")
    async with httpx.AsyncClient(
        verify=client_ctx, trust_env=False, follow_redirects=False
    ) as tls_client:
        with pytest.raises(PageFetchError) as exc_info:
            await fetch_html(
                f"https://jobs.example.test:{port}/",
                client=tls_client,
                resolver=resolver_for({"jobs.example.test": ["127.0.0.1"]}),
            )

    assert exc_info.value.reason == "unreachable"
    assert isinstance(exc_info.value.__cause__, httpx.ConnectError)
    assert seen_sni == ["jobs.example.test"]
