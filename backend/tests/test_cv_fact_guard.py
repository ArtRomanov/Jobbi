"""`unsupported_names`: names an edit adds that the candidate never claimed."""

import pytest

from app.services.cv_fact_guard import unsupported_names
from evals.cv_chat.fixtures import CV, VACANCY

_REWORDED_PROFILE = (
    "Senior frontend engineer with 8 years building React and TypeScript apps, "
    "focused on performance and design systems."
)


def _check(new_text: str, *user_texts: str) -> list[str]:
    return unsupported_names(
        new_text, cv=CV, user_texts=list(user_texts), job_post=VACANCY
    )


def test_job_post_stack_copied_into_skills_is_caught() -> None:
    """Live eval 2026-11-25 (after3, adapt): the model's skills edit."""
    skills = (
        "**Frontend:** TypeScript, React, Next.js, React Query, Redux, JavaScript, "
        "Vue 3, HTML, CSS, Sass\n**Testing:** Testing Library, Jest, Playwright"
    )
    assert _check(skills) == ["Next.js", "React Query", "Testing Library"]


def test_names_the_user_gave_are_supported() -> None:
    skills = "**Frontend:** TypeScript, React, Next.js, Vue 3"
    assert _check(skills, "Add next.js to my skills") == []


def test_invented_camel_case_tool_is_caught_without_a_job_post() -> None:
    text = "- **Rebuilt the checkout in React with TanStack Table:** cut bundle by 38%."
    assert unsupported_names(text, cv=CV, user_texts=[], job_post="") == ["TanStack"]


@pytest.mark.parametrize(
    "text",
    [
        # Rewording of what the CV says, in the job post's words.
        _REWORDED_PROFILE,
        "Frontend engineer working fully remotely across the EU.",
        "Built complex UIs and REST APIs, e.g. the merchant dashboard.",
        "**Frontend:** React, TypeScript, GraphQL, Node.js",
        "Owner of a shared component library for 5 product teams.",
    ],
)
def test_supported_or_generic_text_passes(text: str) -> None:
    assert _check(text) == []


def test_job_post_acronym_is_caught() -> None:
    assert _check("Built accessible UIs (WCAG 2.1 AA).") == ["WCAG"]
