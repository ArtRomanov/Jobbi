"""The CV structure post-check (backlog #27): outline, losses, explicit asks."""

import pytest

from app.services.chat_tools import CvEdit
from app.services.cv_structure import (
    Problem,
    asked_for,
    edit_problems,
    outline_problems,
    read_outline,
    repair_problems_text,
    structure_warning,
    unrequested_problems,
)

CV = """# Alex Morgan
Senior Frontend Engineer
alex@example.com · Lisbon

## PROFILE

Frontend engineer with 8 years of experience.

## EXPERIENCE

### Lead Frontend Engineer — Northwind Pay
Mar 2021 – Present

#### Checkout rebuild

- **Rebuilt the checkout:** cut bundle size by 38%. **Scope:** 3 engineers.

### Frontend Engineer — Bluefin Retail
Jun 2017 – Feb 2021

- **Moved pages to SSR:** LCP 4.1s to 1.9s. **Scope:** 15k pages.

## CERTIFICATIONS

- AWS Certified Cloud Practitioner (2022)
"""

CERTS = "## CERTIFICATIONS\n\n- AWS Certified Cloud Practitioner (2022)\n"


def _replace(before: str, after: str) -> CvEdit:
    return CvEdit(
        op="replace",
        before_text=before,
        after_text=after,
        position=None,
        anchor_text=None,
    )


def _remove(before: str) -> CvEdit:
    return CvEdit(
        op="remove", before_text=before, after_text="", position=None, anchor_text=None
    )


# ---------------------------------------------------------------------------
# Outline
# ---------------------------------------------------------------------------


def test_read_outline_finds_header_sections_entries_and_bullets() -> None:
    outline = read_outline(CV)

    assert outline.header == "Alex Morgan"
    assert outline.sections == ("PROFILE", "EXPERIENCE", "CERTIFICATIONS")
    assert outline.entries == (
        "Lead Frontend Engineer — Northwind Pay",
        "Checkout rebuild",
        "Frontend Engineer — Bluefin Retail",
    )
    assert outline.bullets == 3


@pytest.mark.parametrize(
    ("line", "level_text"),
    [
        ("   ## Skills", ("sections", "Skills")),
        ("## Skills ##", ("sections", "Skills")),
        ("#### Project X", ("entries", "Project X")),
    ],
)
def test_read_outline_follows_commonmark_headings(
    line: str, level_text: tuple[str, str]
) -> None:
    field, text = level_text
    assert getattr(read_outline(line), field) == (text,)


@pytest.mark.parametrize("line", ["##Skills", "    ## Code block", "#hashtag"])
def test_read_outline_ignores_non_headings(line: str) -> None:
    outline = read_outline(line)
    assert outline.sections == () and outline.header is None


def test_plain_text_cv_has_an_empty_outline() -> None:
    outline = read_outline("Alex Morgan\nExperience\nLead engineer at Northwind")
    assert (outline.header, outline.sections, outline.entries) == (None, (), ())


# ---------------------------------------------------------------------------
# Losses
# ---------------------------------------------------------------------------


def test_removed_section_is_a_problem() -> None:
    assert outline_problems(CV, CV.replace(CERTS, "")) == [
        Problem("section_removed", "CERTIFICATIONS")
    ]


def test_renamed_section_is_a_problem() -> None:
    after = CV.replace("## PROFILE", "## SUMMARY")
    assert outline_problems(CV, after) == [
        Problem("section_renamed", "PROFILE", "SUMMARY")
    ]


def test_case_and_emphasis_changes_are_not_a_rename() -> None:
    after = CV.replace("## PROFILE", "## **Profile**")
    assert outline_problems(CV, after) == []


def test_lost_entry_heading_is_a_problem() -> None:
    after = CV.replace("### Frontend Engineer — Bluefin Retail\n", "")
    assert outline_problems(CV, after) == [
        Problem("entry_lost", "Frontend Engineer — Bluefin Retail")
    ]


def test_lost_project_heading_is_a_problem() -> None:
    after = CV.replace("#### Checkout rebuild\n", "Checkout rebuild\n")
    assert outline_problems(CV, after) == [Problem("entry_lost", "Checkout rebuild")]


def test_reworded_entry_heading_is_not_lost() -> None:
    after = CV.replace("— Northwind Pay", "(React) — Northwind Pay")
    assert outline_problems(CV, after) == []


def test_lost_header_is_a_problem() -> None:
    after = CV.replace("# Alex Morgan\n", "Alex Morgan\n")
    assert outline_problems(CV, after) == [Problem("header_lost", "Alex Morgan")]


def test_structuring_a_plain_text_cv_breaks_nothing() -> None:
    plain = "Alex Morgan\nProfile\nFrontend engineer.\nSkills\nReact"
    structured = "# Alex Morgan\n## Profile\nFrontend engineer.\n## Skills\n- React"
    assert outline_problems(plain, structured) == []


def test_shortening_inside_sections_breaks_nothing() -> None:
    after = CV.replace(" with 8 years of experience", "").replace(
        "- **Moved pages to SSR:** LCP 4.1s to 1.9s. **Scope:** 15k pages.\n", ""
    )
    assert outline_problems(CV, after) == []


# ---------------------------------------------------------------------------
# Dry run of one edit
# ---------------------------------------------------------------------------


def test_edit_problems_dry_runs_the_edit() -> None:
    assert edit_problems(CV, _remove(CERTS)) == [
        Problem("section_removed", "CERTIFICATIONS")
    ]


def test_edit_problems_inserting_a_section_breaks_nothing() -> None:
    insert = CvEdit(
        op="insert",
        before_text="",
        after_text="## LANGUAGES\n\nEnglish (C1)",
        position="end",
        anchor_text=None,
    )
    assert edit_problems(CV, insert) == []


@pytest.mark.parametrize("before", ["not in the CV", "- **"])
def test_edit_that_cannot_apply_has_no_problems(before: str) -> None:
    # Missing or repeated passage: Accept rejects the card anyway.
    assert edit_problems(CV, _replace(before, "x")) == []


def test_edit_problems_works_on_crlf_cv() -> None:
    crlf = CV.replace("\n", "\r\n")
    assert edit_problems(crlf, _remove(CERTS)) == [
        Problem("section_removed", "CERTIFICATIONS")
    ]


# ---------------------------------------------------------------------------
# The user's explicit request
# ---------------------------------------------------------------------------

_CERTS_GONE = Problem("section_removed", "CERTIFICATIONS")


@pytest.mark.parametrize(
    "message",
    [
        "Remove the CERTIFICATIONS section.",
        "please delete certifications",
        "Drop the certification section",
        "get rid of Certifications",
        "Убери раздел CERTIFICATIONS",
        "удали certifications, пожалуйста",
        "Нужно убрать CERTIFICATIONS",
    ],
)
def test_explicit_removal_is_asked_for(message: str) -> None:
    assert asked_for(_CERTS_GONE, message)


@pytest.mark.parametrize(
    "message",
    [
        "Make the CV shorter",
        "Adapt my CV to this vacancy",
        "Remove the second bullet at Northwind",  # a verb, but not this section
        "Shorten the certifications",  # the section, but no removal verb
        "Сделай CV короче",
    ],
)
def test_other_messages_do_not_ask_for_the_removal(message: str) -> None:
    assert not asked_for(_CERTS_GONE, message)


def test_entry_removal_is_asked_for_by_company_name() -> None:
    entry = Problem("entry_lost", "Frontend Engineer — Bluefin Retail")
    assert asked_for(entry, "Remove the Bluefin Retail job")
    assert asked_for(entry, "удали опыт в Bluefin Retail")
    assert not asked_for(entry, "Remove the Northwind Pay job")


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Rename PROFILE to SUMMARY", True),
        ("Переименуй раздел profile в Summary", True),
        ("Merge profile into the summary", True),
        ("Rewrite the profile", False),
    ],
)
def test_rename_is_asked_for_with_a_rename_verb(message: str, expected: bool) -> None:
    rename = Problem("section_renamed", "PROFILE", "SUMMARY")
    assert asked_for(rename, message) is expected


def test_unrequested_problems_drops_what_the_user_asked_for() -> None:
    edit = _remove(CERTS)
    assert unrequested_problems(CV, edit, "Remove the CERTIFICATIONS section") == []
    assert unrequested_problems(CV, edit, "Shorten my CV") == [_CERTS_GONE]


# ---------------------------------------------------------------------------
# Texts
# ---------------------------------------------------------------------------


def test_structure_warning_in_english_and_russian() -> None:
    assert structure_warning([_CERTS_GONE], "en") == (
        "This change removes the CERTIFICATIONS section."
    )
    assert structure_warning([_CERTS_GONE], "ru") == (
        "Эта правка удаляет раздел CERTIFICATIONS."
    )


def test_structure_warning_joins_problems_and_is_none_without_them() -> None:
    problems = [
        Problem("section_renamed", "PROFILE", "SUMMARY"),
        Problem("entry_lost", "Checkout rebuild"),
    ]
    assert structure_warning(problems, "en") == (
        "This change renames the PROFILE section to SUMMARY. "
        "This change removes the entry “Checkout rebuild”."
    )
    assert structure_warning([], "en") is None


def test_repair_problems_text_names_every_problem() -> None:
    text = repair_problems_text([_CERTS_GONE, Problem("header_lost", "Alex Morgan")])
    assert text == (
        'an edit removes the CERTIFICATIONS section; an edit removes the "# Alex '
        'Morgan" header line'
    )
