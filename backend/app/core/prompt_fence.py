"""Fence untrusted text as data inside an LLM prompt.

Untrusted text (scraped posts, user notes, CV content) goes between an open and
a close marker built from "<<<" and ">>>". `defang` shortens every run of three
or more "<" or ">" to two, so the text can neither close its own block nor open
a fake one.
"""

import re

_FENCE_CHARS_RE = re.compile(r"<{3,}|>{3,}")


def defang(text: str) -> str:
    """Remove fence-like sequences so untrusted text cannot break out of its fence."""
    return _FENCE_CHARS_RE.sub(lambda m: m.group(0)[0] * 2, text)


def fence_open(label: str) -> str:
    return f"<<<DATA {label}>>>"


def fence_close(label: str) -> str:
    return f"<<<END {label}>>>"


def fence(label: str, body: str) -> str:
    """Wrap `body` (defanged here) in DATA/END markers named `label`."""
    return "\n".join([fence_open(label), defang(body), fence_close(label)])
