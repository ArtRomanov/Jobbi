"""Catch CV edits that add names the candidate never claimed (backlog #29).

The chat model, asked to tailor a CV, tends to copy the job post's stack into
the CV ("Next.js, React Query, Testing Library") even when told not to. This
module finds such names in an edit's new text, so the chat can leave the edit
out and say why. It only looks at names, never at wording: a name counts as
supported when the CV or one of the user's messages mentions it.

Two kinds of names are checked, both cheap to spot without a word list:
- tech-shaped tokens in the new text: camelCase ("TanStack") or dotted
  ("Next.js");
- names from the job post: runs of two or more Capitalised words ("React
  Query", "Testing Library") and all-caps or camelCase tokens ("WCAG", "SaaS").

Single capitalised words ("Python") and numbers are not checked: telling them
from ordinary words or rewording ("half" -> "50%") needs more than a regex.
"""

import re

_TECH_TOKEN = re.compile(
    r"\b[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z][A-Za-z0-9]*)+\b|"  # Next.js, D3.js
    r"\b[A-Za-z]*[a-z][A-Z][A-Za-z0-9]*\b"  # TanStack, GraphQL
)
_WORD = r"[A-Z][A-Za-z0-9+#]*(?:\.[A-Za-z0-9]+)*"
_CAPITALISED_RUN = re.compile(rf"\b{_WORD}(?:[ \t]+{_WORD})+")
_ACRONYM = re.compile(r"\b[A-Z][A-Z0-9]+\b")
# Generic acronyms and regions: rewording or location, not a claimed skill.
_GENERIC = {
    "UI", "UX", "API", "CI", "CD", "PR", "QA", "CV", "SPA", "KPI", "MVP",
    "EU", "US", "UK", "EMEA",
}  # fmt: skip


def _is_name(token: str) -> bool:
    if token.upper().removesuffix("S") in _GENERIC:
        return False
    # "e.g", "i.e": every dotted part is a single letter.
    return not all(len(part) <= 1 for part in token.split("."))


def _job_post_names(job_post: str) -> set[str]:
    names = set(_CAPITALISED_RUN.findall(job_post))
    names.update(_ACRONYM.findall(job_post))
    names.update(_TECH_TOKEN.findall(job_post))
    return {n for n in names if _is_name(n)}


def _mentions(haystack: str, name: str) -> bool:
    pattern = rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])"
    return re.search(pattern, haystack, re.IGNORECASE) is not None


def unsupported_names(
    new_text: str, *, cv: str, user_texts: list[str], job_post: str
) -> list[str]:
    """Names in `new_text` that neither the CV nor the user mentions.

    Sorted, without duplicates; empty when the edit adds no such name.
    """
    known = "\n".join([cv, *user_texts])
    candidates = set(_TECH_TOKEN.findall(new_text))
    candidates.update(
        name for name in _job_post_names(job_post) if _mentions(new_text, name)
    )
    unsupported = {
        name for name in candidates if _is_name(name) and not _mentions(known, name)
    }
    # "React Query" also matches its parts; keep only the longest names.
    return sorted(
        name
        for name in unsupported
        if not any(name != other and name in other for other in unsupported)
    )
