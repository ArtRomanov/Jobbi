"""Shared HTTP and text helpers for the Greenhouse / Lever / Teamtailor fetchers.

``html_to_text`` is also used by ``web_job``. It parses with lxml (which
stops at a fixed nesting depth, ~255 levels; a deeper document reads as
empty) and builds the text in one linear pass, so a hostile description
(30 000 sibling blocks, thousands of nesting levels, megabytes of markup)
costs time proportional to its size. It is CPU work: async callers run it
through ``asyncio.to_thread``.
"""

import json
import re
from typing import Any

import httpx
from lxml import etree
from lxml import html as lxml_html

from app.discovery.fetchers.errors import BoardReadError
from app.discovery.normalize import normalize_url

USER_AGENT = "Jobbi/1.0"
REQUEST_TIMEOUT_SECONDS = 15.0
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # measured on the decompressed body
MAX_TEXT_CHARS = 20_000
# Column sizes of `vacancies` / `vacancy_seen_keys` (PostgreSQL enforces them;
# one oversized value would fail the whole store transaction every run).
MAX_KEY_CHARS = 255
MAX_URL_CHARS = 2048
MAX_NAME_CHARS = 255
# Remote ids go into logs clipped to this length.
MAX_LOGGED_ID_CHARS = 64

# Board tokens and Lever slugs only ever go into a URL path on a fixed host.
# Anything else (slashes, dots, encoded chars) cannot be a real board.
_HANDLE_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")

# Elements that start and end a line of text; inline ones (<b>, <a>) don't.
BLOCK_TAGS = frozenset(
    {
        "p", "div", "li", "ul", "ol", "dl", "dt", "dd", "tr", "table",
        "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "main",
        "header", "footer", "aside", "nav", "blockquote", "pre", "form",
        "fieldset", "figure", "figcaption", "address", "hr", "br",
    }
)  # fmt: skip
# Elements whose content is never visible text.
NOISE_TAGS = ("script", "style", "noscript", "template", "svg", "iframe")
_SPACES_RE = re.compile(r"[ \t\u00a0]+")  # \u00a0 = non-breaking space


def check_handle(handle: str) -> str:
    """Return ``handle`` if it is safe to put into a board API path.

    Raises:
        BoardReadError: ``not_found`` if the handle cannot be a board name.
    """
    if not _HANDLE_RE.fullmatch(handle):
        raise BoardReadError("not_found")
    return handle


async def get_bytes(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, str | int] | None = None,
    headers: dict[str, str] | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> bytes:
    """GET ``url`` and return the raw body (decompressed, at most ``max_bytes``).

    Redirects are not followed, so the request never leaves the fixed host.
    ``max_bytes`` defaults to 5 MB; only a fixed-host adapter with measured
    larger answers (Ashby) passes more.

    Raises:
        BoardReadError: ``not_found`` on 404; ``unreachable`` on any other
            non-200 status, transport error/timeout or a body over the size
            cap (after decompression).
    """
    request_headers = {"User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)
    try:
        async with client.stream(
            "GET",
            url,
            params=params,
            headers=request_headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as response:
            if response.status_code == 404:
                raise BoardReadError("not_found")
            if response.status_code != 200:
                raise BoardReadError("unreachable")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise BoardReadError("unreachable")
    except httpx.HTTPError as exc:
        raise BoardReadError("unreachable") from exc
    return bytes(body)


async def get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, str | int] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """GET ``url`` and return the parsed JSON body.

    Raises:
        BoardReadError: as ``get_bytes``; also ``unreachable`` on invalid JSON.
    """
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    body = await get_bytes(client, url, params=params, headers=request_headers)
    return parse_json_body(body)


def parse_json_body(body: bytes) -> Any:
    """Parse a JSON body from a board API.

    Raises:
        BoardReadError: ``unreachable`` for invalid JSON, undecodable bytes
            or nesting deeper than the parser allows (``RecursionError``).
    """
    try:
        return json.loads(body)
    except (ValueError, RecursionError) as exc:
        raise BoardReadError("unreachable") from exc


def parse_html(markup: str) -> lxml_html.HtmlElement | None:
    """The document root, or None for an empty or unreadable document."""
    parser = lxml_html.HTMLParser(
        encoding="utf-8", remove_comments=True, remove_pis=True, no_network=True
    )
    try:
        return lxml_html.document_fromstring(
            markup.encode("utf-8", "replace"), parser=parser
        )
    except (etree.LxmlError, ValueError):
        return None


def element_text(element: etree._Element) -> str:
    """Plain text with one block element per line (one linear pass)."""
    parts: list[str] = []
    for event, node in etree.iterwalk(element, events=("start", "end")):
        is_block = node.tag in BLOCK_TAGS
        if event == "start":
            if is_block:
                parts.append("\n")
            if node.text:
                parts.append(node.text)
        else:
            if is_block:
                parts.append("\n")
            if node.tail and node is not element:
                parts.append(node.tail)
    lines = (_SPACES_RE.sub(" ", line).strip() for line in "".join(parts).splitlines())
    return "\n".join(line for line in lines if line)


def html_to_text(markup: str) -> str:
    """Convert an HTML fragment to plain text with one block per line.

    Entities are decoded, script/style-like elements dropped; markup lxml
    cannot read gives "". Linear in the size of ``markup``.
    """
    if not markup.strip():
        return ""
    root = parse_html(markup)
    if root is None:
        return ""
    etree.strip_elements(root, *NOISE_TAGS, with_tail=False)
    body = root.find("body")
    return element_text(body if body is not None else root)


def cap_text(text: str) -> str:
    """Cut stored post text to ``MAX_TEXT_CHARS``."""
    return text[:MAX_TEXT_CHARS]


def fits_columns(key: str, url: str) -> bool:
    """True if the seen-key and the URL (raw and normalized) fit their columns."""
    return (
        len(key) <= MAX_KEY_CHARS
        and len(url) <= MAX_URL_CHARS
        and len(normalize_url(url)) <= MAX_URL_CHARS
    )


def cap_name(value: Any) -> str | None:
    """A non-empty string cut to ``MAX_NAME_CHARS``; None otherwise."""
    return value[:MAX_NAME_CHARS] if isinstance(value, str) and value else None


def loggable_id(value: Any) -> str:
    """A remote id as a short string, safe to put in a log line."""
    return str(value)[:MAX_LOGGED_ID_CHARS]
