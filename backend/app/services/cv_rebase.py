"""Re-aim a CV change card at a CV that changed after the card was made.

Two cards of one reply often quote the same paragraph. Accepting the first
changes it, so the second card's `before_text` is no longer in the CV. The
second card's own change usually still makes sense, though: it touched another
part of the paragraph. This module finds where that change goes now, like a
3-way merge (base = the card's before text, ours = its after text, theirs =
the current CV), and gives up whenever the answer is not clear.

Pure functions; every input is expected with LF line breaks.

- `rebase_replace`: the card's change is split into hunks (runs of changed
  words). Each hunk, with some of the text around it as context, must be
  found exactly once in the CV; the context shrinks step by step (40, 24, 12
  characters) when it is not found, and a second match anywhere means "give
  up". At least half of the card's before text must still be there around
  the hunks, so a paragraph that was rewritten is never patched.
- `rebase_anchor`: an insert's anchor line that was edited is matched to the
  one CV line (or run of lines) that still holds most of it.

A remove card is never re-aimed: deleting text someone else has changed since
is a real conflict.
"""

import re
from difflib import SequenceMatcher

_TOKEN = re.compile(r"\w+|\s+|[^\w\s]")
# Context tried on each side of a hunk, longest first.
CONTEXT_STEPS = (40, 24, 12)
# Changed runs separated by this many unchanged tokens or fewer are one hunk.
_MERGE_GAP_TOKENS = 2
# Share of the card's before text that must still be in the CV around the hunks.
MIN_KEPT_SHARE = 0.5
# Matching runs shorter than this many tokens ("the ", ", ") do not count.
_MIN_RUN_TOKENS = 3
# An edited anchor: share of it still in the line, and overall likeness.
MIN_ANCHOR_COVERAGE = 0.8
MIN_ANCHOR_RATIO = 0.5


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text)


def _offsets(tokens: list[str]) -> list[int]:
    """Character offset of each token, plus the total length at the end."""
    offsets = [0]
    for token in tokens:
        offsets.append(offsets[-1] + len(token))
    return offsets


def _hunks(before: str, after: str) -> list[tuple[int, int, str]]:
    """(start, end, replacement) in `before` characters, in order."""
    old, new = _tokens(before), _tokens(after)
    old_at, new_at = _offsets(old), _offsets(new)
    merged: list[list[int]] = []  # [i1, i2, j1, j2] in tokens
    matcher = SequenceMatcher(None, old, new, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if merged and i1 - merged[-1][1] <= _MERGE_GAP_TOKENS:
            merged[-1][1], merged[-1][3] = i2, j2
        else:
            merged.append([i1, i2, j1, j2])
    return [
        (old_at[i1], old_at[i2], after[new_at[j1] : new_at[j2]])
        for i1, i2, j1, j2 in merged
    ]


def _positions(content: str, needle: str) -> list[int]:
    """Every start of `needle` in `content`, overlaps included (up to two)."""
    found: list[int] = []
    start = content.find(needle)
    while start != -1 and len(found) < 2:
        found.append(start)
        start = content.find(needle, start + 1)
    return found


def _locate(content: str, before: str, start: int, end: int) -> tuple[int, int] | None:
    """Where the hunk `before[start:end]` is in `content`, with its context.

    Returns the (start, end) in `content` of the context + hunk + context
    match, or None when it is missing or not unique.
    """
    for size in CONTEXT_STEPS:
        lo, hi = max(0, start - size), min(len(before), end + size)
        found = _positions(content, before[lo:hi])
        if len(found) > 1:
            return None  # A shorter context would only match more places.
        if found:
            return found[0] + (start - lo), found[0] + (end - lo)
    return None


def _kept_share(before: str, window: str) -> float:
    """Share of `before` (in characters) still found, in order, in `window`."""
    old, cur = _tokens(before), _tokens(window)
    matcher = SequenceMatcher(None, old, cur, autojunk=False)
    kept = sum(
        sum(len(t) for t in old[block.a : block.a + block.size])
        for block in matcher.get_matching_blocks()
        if block.size >= _MIN_RUN_TOKENS
    )
    return kept / len(before) if before else 0.0


def rebase_replace(content: str, before: str, after: str) -> tuple[str, str] | None:
    """A (before, after) pair for the current CV with the card's change.

    The new before is a passage found exactly once in `content`; None when
    the change cannot be placed cleanly.
    """
    hunks = _hunks(before, after)
    if not hunks or not before:
        return None
    placed: list[tuple[int, int, str]] = []
    for start, end, replacement in hunks:
        where = _locate(content, before, start, end)
        if where is None:
            return None
        if placed and where[0] < placed[-1][1]:
            return None  # Out of order or overlapping: not the same passage.
        placed.append((*where, replacement))

    # The card's before text must still largely be there around the hunks.
    slack = len(before) // 5
    first_start, last_end = placed[0][0], placed[-1][1]
    lo = max(0, first_start - hunks[0][0] - slack)
    hi = min(len(content), last_end + (len(before) - hunks[-1][1]) + slack)
    if _kept_share(before, content[lo:hi]) < MIN_KEPT_SHARE:
        return None

    # The new passage runs from the first hunk to the last one, widened to
    # whole lines so it stays unique and readable.
    span_start = content.rfind("\n", 0, first_start) + 1
    line_end = content.find("\n", last_end)
    span_end = len(content) if line_end == -1 else line_end
    new_before = content[span_start:span_end]
    parts: list[str] = []
    cursor = span_start
    for start, end, replacement in placed:
        parts += [content[cursor:start], replacement]
        cursor = end
    parts.append(content[cursor:span_end])
    if len(_positions(content, new_before)) != 1:
        return None
    return new_before, "".join(parts)


def rebase_anchor(content: str, anchor: str) -> str | None:
    """The one run of CV lines that is the anchor after an edit, or None."""
    anchor = anchor.strip("\n")
    if not anchor:
        return None
    lines = content.split("\n")
    count = anchor.count("\n") + 1
    hits: list[str] = []
    for i in range(len(lines) - count + 1):
        window = "\n".join(lines[i : i + count])
        matcher = SequenceMatcher(None, anchor, window, autojunk=False)
        kept = sum(block.size for block in matcher.get_matching_blocks())
        if (
            kept / len(anchor) >= MIN_ANCHOR_COVERAGE
            and matcher.ratio() >= MIN_ANCHOR_RATIO
        ):
            hits.append(window)
    if len(hits) != 1 or len(_positions(content, hits[0])) != 1:
        return None
    return hits[0]
