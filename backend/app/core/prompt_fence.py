"""Fence untrusted text as data inside an LLM prompt.

Untrusted text (scraped posts, user notes, CV content) goes between an open and
a close marker built from "<<<" and ">>>". `defang` shortens every run of three
or more "<" or ">" to two, so the text can neither close its own block nor open
a fake one.

Look-alikes count too: a run may use any character that NFKC folds to "<" or
">" (fullwidth "＜", small-form "﹤") and may hide invisible format characters
(Unicode category Cf, e.g. zero-width space) between them. Only such runs are
rewritten; every other character is left exactly as it was.
"""

import re
import sys
import unicodedata
from functools import cache


@cache
def _fence_run_re() -> re.Pattern[str]:
    """Built on first use: scanning every code point takes a few hundred ms."""
    lt: list[str] = []
    gt: list[str] = []
    invisible: list[str] = []
    for code in range(sys.maxunicode + 1):
        ch = chr(code)
        if unicodedata.category(ch) == "Cf":
            invisible.append(ch)
            continue
        folded = unicodedata.normalize("NFKC", ch)
        if folded == "<":
            lt.append(ch)
        elif folded == ">":
            gt.append(ch)

    def char_class(chars: list[str]) -> str:
        return "[" + "".join(re.escape(c) for c in chars) + "]"

    gap = char_class(invisible) + "*"

    def run(brackets: list[str]) -> str:
        bracket = char_class(brackets)
        return f"{bracket}(?:{gap}{bracket}){{2,}}"

    return re.compile(f"(?P<lt>{run(lt)})|(?P<gt>{run(gt)})")


def defang(text: str) -> str:
    """Remove fence-like sequences so untrusted text cannot break out of its fence."""
    return _fence_run_re().sub(lambda m: "<<" if m.group("lt") else ">>", text)


def fence_open(label: str) -> str:
    return f"<<<DATA {label}>>>"


def fence_close(label: str) -> str:
    return f"<<<END {label}>>>"


def fence(label: str, body: str) -> str:
    """Wrap `body` (defanged here) in DATA/END markers named `label`."""
    return "\n".join([fence_open(label), defang(body), fence_close(label)])
