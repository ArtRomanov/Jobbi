"""Shared HTTP and text helpers for the Greenhouse / Lever board fetchers."""

import html
import json
import re
from typing import Any

import httpx

from app.discovery.fetchers.errors import BoardReadError

USER_AGENT = "Jobbi/1.0"
REQUEST_TIMEOUT_SECONDS = 15.0
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # measured on the decompressed body
MAX_TEXT_CHARS = 20_000

# Board tokens and Lever slugs only ever go into a URL path on a fixed host.
# Anything else (slashes, dots, encoded chars) cannot be a real board.
_HANDLE_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")

_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_TAG_RE = re.compile(
    r"</?(?:p|div|br|li|ul|ol|h[1-6]|tr|table)\b[^>]*>", re.IGNORECASE
)
_BLOCK_TAGS = [
    "p",
    "div",
    "li",
    "ul",
    "ol",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "tr",
    "table",
]
_SPACES_RE = re.compile(r"[ \t\u00a0]+")  # \u00a0 = non-breaking space


def check_handle(handle: str) -> str:
    """Return ``handle`` if it is safe to put into a board API path.

    Raises:
        BoardReadError: ``not_found`` if the handle cannot be a board name.
    """
    if not _HANDLE_RE.fullmatch(handle):
        raise BoardReadError("not_found")
    return handle


async def get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, str | int] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """GET ``url`` and return the parsed JSON body.

    Redirects are not followed, so the request never leaves the fixed host.

    Raises:
        BoardReadError: ``not_found`` on 404; ``unreachable`` on any other
            non-200 status, transport error/timeout, body over the size cap
            (after decompression) or invalid JSON.
    """
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
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
                if len(body) > MAX_RESPONSE_BYTES:
                    raise BoardReadError("unreachable")
    except httpx.HTTPError as exc:
        raise BoardReadError("unreachable") from exc
    try:
        return json.loads(body)
    except ValueError as exc:
        raise BoardReadError("unreachable") from exc


def html_to_text(markup: str) -> str:
    """Convert an HTML fragment to plain text with one block per line."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        text = html.unescape(_TAG_RE.sub("", _BLOCK_TAG_RE.sub("\n", markup)))
    else:
        soup = BeautifulSoup(markup, "html.parser")
        # Line breaks only around block elements, so inline tags such as
        # <strong> stay inside their sentence.
        for tag in soup.find_all(_BLOCK_TAGS):
            tag.insert_after("\n")
        for br in soup.find_all("br"):
            br.replace_with("\n")
        text = soup.get_text()
    lines = (_SPACES_RE.sub(" ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def cap_text(text: str) -> str:
    """Cut stored post text to ``MAX_TEXT_CHARS``."""
    return text[:MAX_TEXT_CHARS]
