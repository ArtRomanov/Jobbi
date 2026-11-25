"""The CV chat eval's scorers (backlog #29). Pure: no Groq, no database."""

import pytest

from evals.cv_chat.fixtures import CV, PROFILE_TEXT, VACANCY
from evals.cv_chat.scenarios import SCENARIOS
from evals.cv_chat.scoring import (
    Check,
    Request,
    Scenario,
    Turn,
    TurnOutcome,
    described_edits,
    foreign_tools,
    invented_facts,
    outline,
    reply_matches_cards,
    run_check,
    score_scenario,
    section_body,
)


def test_fixture_profile_text_is_in_the_cv() -> None:
    assert PROFILE_TEXT in CV


def test_outline_of_the_fixture_cv() -> None:
    assert outline(CV) == {
        "sections": ["PROFILE", "SKILLS", "EXPERIENCE", "CERTIFICATIONS", "LANGUAGES"],
        "h3": 2,
        "exp_bullets": 8,
        "exp_bullets_action_result_scope": 8,
        "chars": len(CV),
    }


def test_section_body_stops_at_the_next_section() -> None:
    body = section_body(CV, "skills")
    assert "Vue 3" in body
    assert "Northwind" not in body
    assert section_body(CV, "AWARDS") == ""


@pytest.mark.parametrize(
    ("check", "final", "expected"),
    [
        (
            Check("present", "Next.js", "SKILLS"),
            CV.replace("Vite,", "Vite, Next.js,"),
            True,
        ),
        (Check("present", "Next.js", "SKILLS"), CV, False),
        (Check("absent", "Vue 3", "SKILLS"), CV.replace("Vue 3, ", ""), True),
        (Check("absent", "Vue 3"), CV.replace("Vue 3, ", ""), False),
        (Check("shorter", section="PROFILE"), CV.replace(" and e-commerce", ""), True),
        (Check("shorter"), CV, False),
        (Check("sections_kept"), CV, True),
        (Check("sections_kept"), CV.replace("## LANGUAGES", "LANGUAGES"), False),
        (Check("sections_kept", "LANGUAGES"), CV.replace("## LANGUAGES", ""), True),
        (Check("h3_unchanged"), CV + "\n### Dev — Acme\n", False),
    ],
)
def test_run_check(check: Check, final: str, expected: bool) -> None:
    assert run_check(check, original=CV, final=final, last_reply="") is expected


def test_present_ignores_whitespace_differences() -> None:
    final = CV.replace(PROFILE_TEXT, PROFILE_TEXT.replace(". ", ".\n"))
    check = Check("present", PROFILE_TEXT)
    assert run_check(check, original=CV, final=final, last_reply="")


def test_reply_checks() -> None:
    ru = "Я убрал Vue 3 из навыков и сократил профиль до одного предложения."
    assert run_check(Check("reply_cyrillic"), original=CV, final=CV, last_reply=ru)
    assert not run_check(
        Check("reply_cyrillic"), original=CV, final=CV, last_reply="Done."
    )
    # Cards only, no text: nothing in the wrong language.
    assert run_check(Check("reply_cyrillic"), original=CV, final=CV, last_reply="")
    asks = "Which company was it, and what did you do there?"
    assert run_check(
        Check("reply_asks_or_explains"), original=CV, final=CV, last_reply=asks
    )
    assert not run_check(
        Check("reply_asks_or_explains"), original=CV, final=CV, last_reply="Done."
    )


def test_cv_no_cyrillic() -> None:
    check = Check("cv_no_cyrillic")
    assert run_check(check, original=CV, final=CV, last_reply="")
    final = CV.replace("Focus on performance", "Фокус на производительности")
    assert not run_check(check, original=CV, final=final, last_reply="")


def test_foreign_tools_finds_other_names_and_imagined_fetching() -> None:
    assert foreign_tools("I called propose_cv_edit twice.") == []
    assert foreign_tools("Let me use get_cv first.") == ["get_cv"]
    assert foreign_tools("I'll re-pull the current CV to quote edits accurately")
    assert foreign_tools("fetching the current CV.")
    assert foreign_tools("Here are two edits for the profile.") == []


def test_described_edits_counts_numbered_items_else_bold_bullets() -> None:
    numbered = "Edits:\n1. **Profile** — x\n2. **Skills** — y\n\n- a note"
    assert described_edits(numbered) == 2
    bullets = "- **Profile:** shortened\n- **Skills:** moved React first\n- note"
    assert described_edits(bullets) == 2
    questions = "Please share:\n- **Job title** and **company**\n- **Dates**"
    assert described_edits(questions) == 0
    assert described_edits("One edit to the profile.") == 0


def test_reply_matches_cards() -> None:
    four = "\n".join(f"{n}. edit {n}" for n in range(1, 5))
    assert not reply_matches_cards(four, 1, expects_change=True)
    assert reply_matches_cards(four, 4, expects_change=True)
    promise = "First, I'll re-pull the current CV."
    assert not reply_matches_cards(promise, 0, expects_change=True)
    assert reply_matches_cards(promise, 0, expects_change=False)


def test_invented_facts_flags_new_numbers_and_tech_names() -> None:
    sources = [CV, VACANCY, "Add Next.js to my skills"]
    texts = [
        "**Migrated** 15k pages from Nuxt to Next.js with React Query in 7 weeks",
        "Senior engineer building React apps, complex UIs and REST APIs",
    ]
    assert invented_facts(texts, sources) == ["7", "Nuxt"]


def test_score_scenario_on_the_live_failure() -> None:
    """The 2026-11-25 live check: 4 edits described, 1 card, an invented fact."""
    scenario = Scenario(
        id="adapt",
        turns=(Turn("Adapt my CV to this vacancy"),),
        requests=(Request("sections kept", (Check("sections_kept"),)),),
    )
    reply = """These four edits close the gap:
1. **Profile** — React wording
2. **Skills** — React first
3. **Northwind Pay** — Storybook
4. **Bluefin Retail** — Next.js (App Router), migrating 15k pages of Nuxt"""
    new_profile = "Senior Frontend Engineer, Nuxt to Next.js migrations."
    outcome = TurnOutcome(
        user="Adapt my CV to this vacancy",
        reply=reply,
        cards=[{"op": "replace", "before": PROFILE_TEXT, "after": new_profile}],
        accepted=1,
    )
    final = CV.replace(PROFILE_TEXT, new_profile)

    scores = score_scenario(
        scenario, [outcome], original=CV, final=final, vacancy=VACANCY
    )

    assert scores["requests_ok"] == 1
    assert scores["did_something"] is True
    assert scores["reply_matches_cards"] is False
    assert scores["invented"] == ["Nuxt"]
    assert scores["vacancy_only"] == ["Next.js"]
    assert scores["passed"] is False


def test_scenarios_have_unique_ids_and_requests() -> None:
    ids = [s.id for s in SCENARIOS]
    assert len(ids) == len(set(ids)) == 8
    assert all(s.requests and s.turns for s in SCENARIOS)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_untouched_cv_fails_every_change_scenario(scenario: Scenario) -> None:
    """Sanity: doing nothing never passes a scenario that asks for a change."""
    outcomes = [TurnOutcome(user=t.text, reply="Sure.") for t in scenario.turns]
    scores = score_scenario(scenario, outcomes, original=CV, final=CV, vacancy=VACANCY)
    # "cannot_do" asks for no change, but "Sure." neither asks nor explains.
    assert scores["passed"] is False
