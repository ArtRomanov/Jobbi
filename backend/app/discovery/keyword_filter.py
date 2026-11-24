"""Pre-AI keyword filter: a post reaches the AI only if it names a keyword.

Inclusive, unlike the old exclude words (removed in backlog #12): one matching
line keeps the whole post, so a digest with one relevant vacancy is still read.
"""

import re
from collections.abc import Iterable
from functools import lru_cache

__all__ = ["keyword_matches"]

# Spaces and hyphens inside a keyword match any run of spaces and hyphens, so
# "front end" also matches "front-end" and "front  end".
_SEPARATORS = re.compile(r"[\s\-]+")


@lru_cache(maxsize=256)
def _compile(keywords: tuple[str, ...]) -> re.Pattern[str] | None:
    """One case-insensitive regex matching any keyword at the start of a word.

    `(?<!\\w)` is the left word boundary; on `str` patterns `\\w` is
    Unicode-aware, so Cyrillic letters count as word characters. There is no
    right boundary: a keyword also matches longer words that start with it
    ("react" in "reactjs", "фронт" in "фронтенда"), which suits a filter that
    keeps posts rather than drops them.
    """
    alternatives = []
    for keyword in keywords:
        parts = [part for part in _SEPARATORS.split(keyword) if part]
        if parts:
            alternatives.append(r"[\s\-]+".join(re.escape(part) for part in parts))
    if not alternatives:
        return None
    return re.compile(rf"(?<!\w)(?:{'|'.join(alternatives)})", re.IGNORECASE)


def keyword_matches(title: str | None, text: str, keywords: Iterable[str]) -> bool:
    """True if the title or text contains any keyword at the start of a word.

    Letter case is ignored. An empty keyword list matches every post (the
    filter is off).
    """
    pattern = _compile(tuple(sorted({keyword.strip() for keyword in keywords})))
    if pattern is None:
        return True
    return any(pattern.search(part) for part in (title, text) if part)
