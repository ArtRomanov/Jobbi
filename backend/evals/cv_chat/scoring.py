"""Deterministic scorers for the CV chat eval. Pure functions, unit tested.

Every check is a heuristic on text, so a failing check is a pointer for a
human to read the saved reply and cards, not a verdict on its own.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from app.services.chat_tools import PROPOSE_CV_EDIT

CheckKind = Literal[
    "present",  # `text` is in the CV (or in `section`)
    "absent",  # `text` is not in the CV (or in `section`)
    "shorter",  # the CV (or `section`) has fewer characters than before
    "sections_kept",  # every original `## ` section is there, minus `text`
    "h3_unchanged",  # same number of `### ` entries as before
    "reply_cyrillic",  # the last reply is written in Cyrillic
    "reply_asks_or_explains",  # the last reply asks a question or says why not
    "cv_no_cyrillic",  # the CV stays in its own language (English here)
]


@dataclass(frozen=True, slots=True)
class Check:
    kind: CheckKind
    text: str = ""
    section: str | None = None


@dataclass(frozen=True, slots=True)
class Request:
    """One distinct thing the user asked for, and how to see it was done."""

    id: str
    checks: tuple[Check, ...]


@dataclass(frozen=True, slots=True)
class Turn:
    text: str
    # A change was asked: the turn must end with at least one card.
    expects_change: bool = True


@dataclass(frozen=True, slots=True)
class Scenario:
    id: str
    turns: tuple[Turn, ...]
    # Scored on the CV after all cards of all turns are accepted.
    requests: tuple[Request, ...]


@dataclass(slots=True, kw_only=True)
class TurnOutcome:
    user: str
    reply: str
    cards: list[dict[str, str | None]] = field(default_factory=list)
    accepted: int = 0
    accept_failed: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CV outline helpers (also reused by the structure checks of backlog #27)
# ---------------------------------------------------------------------------

_H2 = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_H3 = re.compile(r"^###\s+.+$", re.MULTILINE)


def section_names(cv: str) -> list[str]:
    return [name.strip().upper() for name in _H2.findall(cv)]


def section_body(cv: str, name: str) -> str:
    """The text under `## name` up to the next `## ` heading; "" when missing."""
    pattern = re.compile(
        rf"^##\s+{re.escape(name)}\s*$(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    found = pattern.search(cv)
    return found.group(1) if found else ""


def h3_count(cv: str) -> int:
    return len(_H3.findall(cv))


def outline(cv: str) -> dict[str, object]:
    """Structure facts recorded with every result (not scored yet, see #27)."""
    exp = section_body(cv, "EXPERIENCE")
    bullets = re.findall(r"^\s*[-*]\s+(.+)$", exp, re.MULTILINE)
    ars = [b for b in bullets if re.match(r"\*\*[^*]+:\*\*", b) and "**Scope:**" in b]
    return {
        "sections": section_names(cv),
        "h3": h3_count(cv),
        "exp_bullets": len(bullets),
        "exp_bullets_action_result_scope": len(ars),
        "chars": len(cv),
    }


# ---------------------------------------------------------------------------
# Single checks
# ---------------------------------------------------------------------------

_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
_EXPLAINS = re.compile(
    r"\?|can't|cannot|can not|don't have|do not have|no information|not in your cv|"
    r"не могу|нет информации|нет данных|не указан",
    re.IGNORECASE,
)


def _scope(cv: str, section: str | None) -> str:
    return cv if section is None else section_body(cv, section)


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def run_check(check: Check, *, original: str, final: str, last_reply: str) -> bool:
    match check.kind:
        case "present":
            return _norm(check.text) in _norm(_scope(final, check.section))
        case "absent":
            return _norm(check.text) not in _norm(_scope(final, check.section))
        case "shorter":
            return len(_scope(final, check.section)) < len(
                _scope(original, check.section)
            )
        case "sections_kept":
            removed = {s.strip().upper() for s in check.text.split(",") if s.strip()}
            wanted = [s for s in section_names(original) if s not in removed]
            return all(s in section_names(final) for s in wanted)
        case "h3_unchanged":
            return h3_count(final) == h3_count(original)
        case "reply_cyrillic":
            # A cards-only reply (no text) is not in the wrong language.
            text = last_reply.strip()
            return not text or len(_CYRILLIC.findall(text)) > 20
        case "reply_asks_or_explains":
            return bool(_EXPLAINS.search(last_reply))
        case "cv_no_cyrillic":
            return not _CYRILLIC.search(final)
    raise ValueError(f"unknown check kind: {check.kind}")


# ---------------------------------------------------------------------------
# Reply checks
# ---------------------------------------------------------------------------

_SNAKE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
_IMAGINED_ACTION = re.compile(
    r"\b(?:fetch\w*|re-?pull\w*|re-?read\w*|re-?load\w*|re-?check\w* the (?:current )?cv|"
    r"pull(?:ing)? (?:up )?the (?:current |latest )?cv|"
    r"load(?:ing)? the (?:current |latest )?cv)\b|"
    r"загруж\w*|подгруж\w*|перечита\w*",
    re.IGNORECASE,
)


def foreign_tools(reply: str) -> list[str]:
    """Tool names or imagined actions (fetching the CV) the reply mentions."""
    names = [n for n in _SNAKE.findall(reply) if n != PROPOSE_CV_EDIT]
    actions = [m.group(0) for m in _IMAGINED_ACTION.finditer(reply)]
    return names + actions


_NUMBERED = re.compile(r"^\s{0,3}\d+[.)]\s", re.MULTILINE)
_BOLD_BULLET = re.compile(r"^\s{0,3}[-*•]\s+\*\*.*$", re.MULTILINE)
# A bold-led bullet counts as an edit only when it names one ("- **Skills** —
# React moved first"), not when it lists questions ("- **Dates**").
_EDIT_VERB = re.compile(
    r"\b(?:add|remov|replac|rewr|rephras|reword|mov|shorten|cut|drop|swap|"
    r"tighten|trim|reorder|chang|updat|renam|merg|split|emphasi|highlight|"
    r"restor|put)\w*|"
    r"убра|удал|добав|замен|сократ|перепис|перенес|измен|вернул",
    re.IGNORECASE,
)
_PROMISE = re.compile(
    r"\b(?:I'll|I will|let me|I'm going to|I am going to)\b|"
    r"сейчас (?:\w+ )?(?:сделаю|исправлю|изменю|подготовлю|предложу)",
    re.IGNORECASE,
)


def described_edits(reply: str) -> int:
    """How many edits the reply lists: numbered items, else bold-led bullets
    that name an edit.
    """
    numbered = len(_NUMBERED.findall(reply))
    if numbered:
        return numbered
    return sum(1 for b in _BOLD_BULLET.findall(reply) if _EDIT_VERB.search(b))


def reply_matches_cards(reply: str, cards: int, *, expects_change: bool) -> bool:
    """The reply does not describe more edits than it proposed.

    A reply with no cards fails when a change was asked and the reply only
    promises to act ("I'll ...") instead of proposing or explaining.
    """
    if described_edits(reply) > cards:
        return False
    return not (expects_change and cards == 0 and _PROMISE.search(reply))


# ---------------------------------------------------------------------------
# Invented facts
# ---------------------------------------------------------------------------

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9.+#/-]*[A-Za-z0-9+#]|[A-Za-z]")
# Generic acronyms that are rewording, not a new fact.
_GENERIC = {"UI", "UX", "API", "APIS", "PR", "PRS", "QA", "CV", "EU", "SPA", "SPAS"}
TECH_WORDS = {
    "angular", "svelte", "nuxt", "next.js", "nextjs", "remix", "gatsby", "redux",
    "mobx", "zustand", "graphql", "apollo", "relay", "jest", "vitest", "cypress",
    "playwright", "storybook", "webpack", "vite", "rollup", "esbuild", "tailwind",
    "node.js", "nodejs", "deno", "python", "django", "java", "kotlin", "swift",
    "go", "rust", "docker", "kubernetes", "terraform", "aws", "gcp", "azure",
    "firebase", "postgres", "postgresql", "mysql", "mongodb", "redis", "kafka",
    "d3", "d3.js", "highcharts", "echarts", "ag-grid", "wcag", "aria",
}  # fmt: skip


def _is_fact_word(word: str) -> bool:
    if word.casefold() in TECH_WORDS:
        return True
    if word.upper() in _GENERIC or word.upper().removesuffix("S") in _GENERIC:
        return False
    capitals = sum(c.isupper() for c in word)
    camel = re.search(r"[a-z][A-Z]", word) is not None
    dotted = re.search(r"[A-Za-z]\.[A-Za-z]", word) is not None
    return capitals >= 2 or camel or dotted


def invented_facts(new_texts: list[str], sources: list[str]) -> list[str]:
    """Numbers and tech-like names in new text that no source mentions.

    Sources are the original CV, the vacancy and the user's messages.
    """
    haystack = _norm("\n".join(sources))
    known_numbers = set(_NUMBER.findall(haystack))
    found: list[str] = []
    for text in new_texts:
        plain = text.replace("**", " ")
        for number in _NUMBER.findall(plain):
            if number not in known_numbers:
                found.append(number)
        for word in _WORD.findall(plain):
            if _is_fact_word(word) and word.casefold() not in haystack:
                found.append(word)
    return sorted(set(found))


# ---------------------------------------------------------------------------
# Whole scenario
# ---------------------------------------------------------------------------


def score_scenario(
    scenario: Scenario,
    turns: list[TurnOutcome],
    *,
    original: str,
    final: str,
    vacancy: str,
) -> dict[str, object]:
    last_reply = turns[-1].reply if turns else ""
    requests = {
        request.id: all(
            run_check(c, original=original, final=final, last_reply=last_reply)
            for c in request.checks
        )
        for request in scenario.requests
    }
    did_something = all(
        len(outcome.cards) > 0
        for outcome, turn in zip(turns, scenario.turns, strict=True)
        if turn.expects_change
    )
    matches = all(
        reply_matches_cards(
            outcome.reply, len(outcome.cards), expects_change=turn.expects_change
        )
        for outcome, turn in zip(turns, scenario.turns, strict=True)
    )
    tools = sorted({t for outcome in turns for t in foreign_tools(outcome.reply)})
    new_texts = [str(c.get("after") or "") for o in turns for c in o.cards]
    users = [o.user for o in turns]
    invented = invented_facts(new_texts, [original, vacancy, *users])
    # Named only in the job post: a skill the CV never claimed (stricter than
    # `invented`, which accepts the vacancy as a source).
    borrowed = sorted(
        set(invented_facts(new_texts, [original, *users])) - set(invented)
    )
    scores = {
        "requests_ok": sum(requests.values()),
        "requests_total": len(requests),
        "did_something": did_something,
        "reply_matches_cards": matches,
        "no_foreign_tools": not tools,
        "no_invented_facts": not invented,
        "no_vacancy_only_facts": not borrowed,
    }
    passed = (
        scores["requests_ok"] == scores["requests_total"]
        and did_something
        and matches
        and not tools
        and not invented
        and not borrowed
    )
    return {
        **scores,
        "passed": passed,
        "requests": requests,
        "foreign_tools": tools,
        "invented": invented,
        "vacancy_only": borrowed,
        "described_edits": [described_edits(o.reply) for o in turns],
    }
