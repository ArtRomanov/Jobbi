"""Keep the CV's Markdown structure through chat edits (backlog #27).

Pure helpers, no model call, no database:
- `read_outline` reads the CV's skeleton: the `# ` header line, the `## `
  sections, the `###` / `####` entries (jobs, projects) and the `- ` bullets;
- `edit_problems` dry-runs one proposed edit on the CV and lists what it
  breaks: a section gone or renamed, an entry heading lost, the header gone;
- `asked_for` tells whether the user's latest message explicitly asked for
  that (a removal / rename / merge verb plus the section or entry name);
- `structure_warning` is the card's warning in the conversation language,
  and `repair_problems_text` the English list for the model's repair note.

Only losses count: a plain-text CV that gains headings breaks nothing.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.services.chat_card_service import (
    _PassageMissing,
    _PassageNotUnique,
    apply_card_edit,
)
from app.services.chat_guard_notes import Language
from app.services.chat_tools import CvEdit

# CommonMark ATX heading: up to 3 spaces in, 1-6 "#", a space, the text, and
# an optional closing run of "#". The closing run is cut in `_heading_text`:
# a lazy text group followed by optional whitespace runs backtracks
# quadratically on a long run of spaces (a 20k-char line took seconds).
_HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+)$")
_BULLET = re.compile(r"^\s*[-*+][ \t]+\S")

ProblemKind = Literal["section_removed", "section_renamed", "entry_lost", "header_lost"]


@dataclass(frozen=True, slots=True)
class CvOutline:
    """The structure of a Markdown CV, in document order."""

    header: str | None  # the first `# ` heading's text
    sections: tuple[str, ...]  # `## ` heading texts
    entries: tuple[str, ...]  # `###` and `####` heading texts
    bullets: int


@dataclass(frozen=True, slots=True)
class Problem:
    """One structure loss caused by an edit."""

    kind: ProblemKind
    name: str  # the section, entry or header text that was lost
    new_name: str | None = None  # section_renamed: the new heading


def _heading_text(raw: str) -> str:
    """The heading text without its optional closing `#` run (`## Skills ##`)."""
    text = raw.rstrip(" \t")
    without_hashes = text.rstrip("#")
    if without_hashes != text and without_hashes[-1:] in (" ", "\t"):
        text = without_hashes
    return text.strip()


def read_outline(cv: str) -> CvOutline:
    header: str | None = None
    sections: list[str] = []
    entries: list[str] = []
    bullets = 0
    for line in cv.splitlines():
        if heading := _HEADING.match(line):
            level, text = len(heading.group(1)), _heading_text(heading.group(2))
            if level == 1 and header is None:
                header = text
            elif level == 2:
                sections.append(text)
            elif level in (3, 4):
                entries.append(text)
        elif _BULLET.match(line):
            bullets += 1
    return CvOutline(
        header=header, sections=tuple(sections), entries=tuple(entries), bullets=bullets
    )


def _key(name: str) -> str:
    """Headings compare by words, ignoring case and Markdown emphasis."""
    return " ".join(name.replace("*", " ").replace("_", " ").split()).casefold()


def _missing(before: Sequence[str], after: Sequence[str]) -> list[str]:
    """Items of `before` not in `after`, counting repeats (a multiset diff)."""
    left = [_key(a) for a in after]
    missing: list[str] = []
    for name in before:
        key = _key(name)
        if key in left:
            left.remove(key)
        else:
            missing.append(name)
    return missing


def outline_problems(before: str, after: str) -> list[Problem]:
    """What `after` lost of the structure of `before`."""
    old, new = read_outline(before), read_outline(after)
    problems: list[Problem] = []
    if old.header is not None and new.header is None:
        problems.append(Problem("header_lost", old.header))

    gone = _missing(old.sections, new.sections)
    added = _missing(new.sections, old.sections)
    for i, name in enumerate(gone):
        # A section swapped for a new heading in the same edit is a rename.
        if i < len(added):
            problems.append(Problem("section_renamed", name, added[i]))
        else:
            problems.append(Problem("section_removed", name))

    # An entry whose heading was reworded is not lost; fewer entries is.
    lost = len(old.entries) - len(new.entries)
    if lost > 0:
        missing = _missing(old.entries, new.entries) or list(old.entries)
        problems += [Problem("entry_lost", name) for name in missing[:lost]]
    return problems


def edit_problems(cv: str, edit: CvEdit) -> list[Problem]:
    """Dry-run `edit` on `cv` (nothing is saved) and list what it breaks.

    An edit that cannot be applied (its passage is missing or not unique)
    breaks nothing here: Accept rejects it anyway.
    """
    try:
        after = apply_card_edit(
            cv,
            op=edit.op,
            before_text=edit.before_text,
            after_text=edit.after_text,
            position=edit.position,
            anchor_text=edit.anchor_text,
        )
    except (_PassageMissing, _PassageNotUnique, ValueError):
        return []
    return outline_problems(cv, after)


# ---------------------------------------------------------------------------
# The user's explicit request
# ---------------------------------------------------------------------------

_REMOVE_VERB = re.compile(
    r"\b(?:delet|remov|drop|get rid of|cut out|leave out)\w*|"
    r"(?<![а-яё])(?:убер|убра|убир|удал|выкин|выброс)[а-яё]*",
    re.IGNORECASE,
)
_RENAME_VERB = re.compile(
    r"\b(?:renam|retitl|merg|combin|join)\w*|"
    r"(?<![а-яё])(?:переимен|назов|объедин|слей|слить)[а-яё]*",
    re.IGNORECASE,
)
# Parts of an entry heading ("Role — Company | City") each count as its name.
_ENTRY_PARTS = re.compile(r"\s+[—–-]\s+|\s*[|,·@]\s*|\s+at\s+", re.IGNORECASE)
_MIN_PART_CHARS = 3


def _mentions(message: str, name: str) -> bool:
    key = _key(name)
    if not key:
        return False
    # "CERTIFICATIONS" is also named by "the certification section".
    stem = key.removesuffix("s") if len(key) > 4 else key
    pattern = rf"(?<!\w){re.escape(stem)}(?:s)?(?!\w)"
    return re.search(pattern, _key(message)) is not None


def _names(problem: Problem) -> list[str]:
    if problem.kind != "entry_lost":
        return [problem.name]
    parts = [p.strip() for p in _ENTRY_PARTS.split(problem.name)]
    return [problem.name, *(p for p in parts if len(p) >= _MIN_PART_CHARS)]


def asked_for(problem: Problem, user_message: str) -> bool:
    """The user's latest message explicitly asks for this structure change.

    True when it has a removal verb (EN/RU: delete, remove, drop, убери,
    удали, убрать ...) and names the section or entry, case-insensitive. A
    rename also counts with a rename / merge verb. Removing the CV header
    must name it as the header line text (the candidate's name).
    """
    verb = _REMOVE_VERB.search(user_message) is not None
    if problem.kind == "section_renamed":
        verb = verb or _RENAME_VERB.search(user_message) is not None
    return verb and any(_mentions(user_message, name) for name in _names(problem))


def unrequested_problems(cv: str, edit: CvEdit, user_message: str) -> list[Problem]:
    """The structure losses of `edit` the user did not ask for."""
    return [p for p in edit_problems(cv, edit) if not asked_for(p, user_message)]


# ---------------------------------------------------------------------------
# Texts
# ---------------------------------------------------------------------------

_WARNING: dict[Language, dict[ProblemKind, str]] = {
    "en": {
        "section_removed": "This change removes the {name} section.",
        "section_renamed": "This change renames the {name} section to {new_name}.",
        "entry_lost": "This change removes the entry “{name}”.",
        "header_lost": "This change removes the CV header line “{name}”.",
    },
    "ru": {
        "section_removed": "Эта правка удаляет раздел {name}.",
        "section_renamed": "Эта правка переименовывает раздел {name} в {new_name}.",
        "entry_lost": "Эта правка удаляет запись «{name}».",
        "header_lost": "Эта правка удаляет заголовок CV «{name}».",
    },
}
_REPAIR: dict[ProblemKind, str] = {
    "section_removed": "an edit removes the {name} section",
    "section_renamed": "an edit renames the {name} section to {new_name}",
    "entry_lost": 'an edit removes the entry heading "{name}"',
    "header_lost": 'an edit removes the "# {name}" header line',
}


def _fill(template: str, problem: Problem) -> str:
    return template.format(name=problem.name, new_name=problem.new_name or "")


def structure_warning(problems: Sequence[Problem], language: Language) -> str | None:
    """The card's warning, one sentence per problem; None when there is none."""
    if not problems:
        return None
    return " ".join(_fill(_WARNING[language][p.kind], p) for p in problems)


def repair_problems_text(problems: Sequence[Problem]) -> str:
    """The problems as one English clause list, for the model's repair note."""
    return "; ".join(_fill(_REPAIR[p.kind], p) for p in problems)
