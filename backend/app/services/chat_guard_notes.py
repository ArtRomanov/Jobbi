"""What the chat says when the fact guard leaves an edit out (backlog #29).

Deterministic text, no model call:
- the note under the reply follows the conversation language, taken from the
  user's latest message (any Cyrillic letter -> Russian, else English);
- the item of the reply that announced a left-out edit gets a short marker,
  so the reply no longer reads as if that change will happen.
"""

import re
from collections.abc import Sequence
from typing import Literal

Language = Literal["en", "ru"]

UNSUPPORTED_NAMES_NOTE: dict[Language, str] = {
    "en": (
        "Left out one suggested change: it adds {names}, which your CV does "
        "not mention. If you have this experience, tell me and I will add it."
    ),
    "ru": (
        "Пункт про {names} не предложил: в вашем CV нет {names}. "
        "Если опыт есть — напишите, добавлю."
    ),
}
NOT_PROPOSED_MARKER: dict[Language, str] = {
    "en": "(not proposed — see below)",
    "ru": "(не предложено — см. ниже)",
}

_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
# A top-level list item: "1. ", "2) ", "- ", "* ", "• " (at most one space in).
_ITEM_START = re.compile(r"^ ?(?:\d+[.)]|[-*•])\s+")
# A sentence: text up to and including its end mark, or up to a line break.
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]*")
# Closing punctuation the marker goes in front of: "line (marker):".
_TRAILING_PUNCT = re.compile(r"[.:;!?]+$")


def reply_language(user_text: str) -> Language:
    """Russian when the user's message has any Cyrillic letter, else English."""
    return "ru" if _CYRILLIC.search(user_text) else "en"


def unsupported_names_note(names: Sequence[str], language: Language) -> str:
    return UNSUPPORTED_NAMES_NOTE[language].format(names=", ".join(names))


def _mentions_any(text: str, names: Sequence[str]) -> bool:
    return any(
        re.search(
            rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", text, re.IGNORECASE
        )
        for name in names
    )


def _items(lines: list[str]) -> list[tuple[int, int]]:
    """(first, last) line index of each top-level list item.

    An item runs on over the lines that follow it, up to the next item, or up
    to a blank line that is not followed by an indented line.
    """
    items: list[tuple[int, int]] = []
    start: int | None = None
    last = 0
    for i, line in enumerate(lines):
        if _ITEM_START.match(line):
            if start is not None:
                items.append((start, last))
            start = last = i
        elif start is None:
            continue
        elif line.strip():
            if lines[i - 1].strip() or line[:1].isspace():
                last = i
            else:
                items.append((start, last))
                start = None
    if start is not None:
        items.append((start, last))
    return items


def _with_marker(segment: str, marker: str) -> str:
    """`segment` with the marker before its closing punctuation, if any."""
    body = segment.rstrip()
    tail = segment[len(body) :]
    punct = _TRAILING_PUNCT.search(body)
    if punct:
        return f"{body[: punct.start()]} {marker}{punct.group()}{tail}"
    return f"{body} {marker}{tail}"


def _mark_item(lines: list[str], names: Sequence[str], marker: str) -> bool:
    """Mark the only list item mentioning `names`. False if none or several."""
    hits = [
        first
        for first, last in _items(lines)
        if _mentions_any("\n".join(lines[first : last + 1]), names)
    ]
    if len(hits) != 1:
        return False
    first = hits[0]
    if marker not in lines[first]:
        lines[first] = _with_marker(lines[first], marker)
    return True


def _mark_sentence(text: str, names: Sequence[str], marker: str) -> str:
    """Mark the only sentence mentioning `names`; unchanged if none or several."""
    hits = [m for m in _SENTENCE.finditer(text) if _mentions_any(m.group(), names)]
    if len(hits) != 1 or marker in hits[0].group():
        return text
    hit = hits[0]
    return text[: hit.start()] + _with_marker(hit.group(), marker) + text[hit.end() :]


def mark_left_out_items(
    reply: str, left_out: Sequence[Sequence[str]], language: Language
) -> str:
    """Mark the reply's item (or sentence) announcing each left-out edit.

    `left_out` holds the unsupported names of each edit the guard left out.
    The item is the only top-level list item that mentions one of the names;
    with no list item, the only sentence that does. When none or several
    match, the reply is left as is (the note below still explains).
    """
    marker = NOT_PROPOSED_MARKER[language]
    lines = reply.split("\n")
    for names in left_out:
        if _mark_item(lines, names, marker):
            continue
        lines = _mark_sentence("\n".join(lines), names, marker).split("\n")
    return "\n".join(lines)
