"""Exclude-word pre-filter: drops posts before they cost an AI call."""

import re
from collections.abc import Iterable
from functools import lru_cache

__all__ = ["excluded"]


@lru_cache(maxsize=256)
def _compile(terms: tuple[str, ...]) -> re.Pattern[str] | None:
    """Build one case-insensitive regex matching any term as a whole word or phrase.

    `(?<!\\w)` / `(?!\\w)` act as word boundaries; on `str` patterns `\\w` is
    Unicode-aware, so Cyrillic letters count as word characters. Unlike `\\b` they
    also work for terms that start or end with punctuation (`c++`, `.net`).
    Whitespace inside a phrase matches any run of whitespace.
    """
    alternatives = []
    for term in terms:
        words = term.split()
        if words:
            alternatives.append(r"\s+".join(re.escape(word) for word in words))
    if not alternatives:
        return None
    # Longest first, so overlapping phrases do not shadow each other.
    alternatives.sort(key=len, reverse=True)
    return re.compile(rf"(?<!\w)(?:{'|'.join(alternatives)})(?!\w)", re.IGNORECASE)


def excluded(title: str | None, text: str, terms: Iterable[str]) -> bool:
    """Return True if the title or text contains any exclude term as a whole word/phrase.

    Letter case is ignored. "java" does not match "javascript"; "office only"
    matches only that phrase.
    """
    pattern = _compile(tuple(sorted({term.strip() for term in terms})))
    if pattern is None:
        return False
    return any(pattern.search(part) for part in (title, text) if part)
