"""The frozen CV form -> text converter in migration 468c8b1a04af (spec 011, 2.2)."""

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "468c8b1a04af_add_cv_content_and_version.py"
)


def _load_migration() -> ModuleType:
    """Import the migration file as a plain module.

    Under pytest the local `backend/alembic/` folder shadows the alembic
    package, so `from alembic import op` gets a stand-in; the converter
    never touches `op`.
    """
    spec = importlib.util.spec_from_file_location("migration_468c8b1a04af", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    alembic_stub = SimpleNamespace(op=SimpleNamespace())
    with patch.dict(sys.modules, {"alembic": alembic_stub}):
        spec.loader.exec_module(module)
    return module


convert: Callable[..., str] = _load_migration().convert_cv_to_text


def _cv(**fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "My CV",
        "personal_info": None,
        "summary": None,
        "work_experience": None,
        "education": None,
        "skills": None,
        "languages": None,
    }
    return {**base, **fields}


_FULL_CV = _cv(
    personal_info={
        "full_name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "+374 99 123456",
        "location": "Yerevan",
        "linkedin_url": "https://linkedin.com/in/jane",
    },
    summary="Frontend developer with 6 years of experience…",
    work_experience=[
        {
            "company": "Acme",
            "role": "Senior Frontend Developer",
            "start_date": "2022-01",
            "end_date": None,
            "is_current": True,
            "description": "Built the design system…",
        },
        {
            "company": "Beta",
            "role": "Frontend Developer",
            "start_date": "2019-03",
            "end_date": "2021-12",
            "is_current": False,
            "description": None,
        },
    ],
    education=[
        {
            "institution": "Yerevan State University",
            "degree": "BSc",
            "field_of_study": "Computer Science",
            "start_year": "2014",
            "end_year": "2018",
            "description": "Thesis on compilers",
        }
    ],
    skills="React, TypeScript, Next.js",
    languages="English (C1), Russian (native)",
)

_FULL_TEXT = """\
# Jane Doe
jane@example.com · +374 99 123456 · Yerevan · https://linkedin.com/in/jane

## Summary
Frontend developer with 6 years of experience…

## Experience
### Senior Frontend Developer — Acme
Jan 2022 – Present
Built the design system…

### Frontend Developer — Beta
Mar 2019 – Dec 2021

## Education
### BSc Computer Science — Yerevan State University
2014 – 2018
Thesis on compilers

## Skills
React, TypeScript, Next.js

## Languages
English (C1), Russian (native)"""


def test_full_cv_matches_the_spec_layout() -> None:
    assert convert(**_FULL_CV) == _FULL_TEXT


def test_every_entered_value_appears_in_the_text() -> None:
    text = convert(**_FULL_CV)

    values = [
        *_FULL_CV["personal_info"].values(),
        _FULL_CV["summary"],
        _FULL_CV["skills"],
        _FULL_CV["languages"],
    ]
    for entry in _FULL_CV["work_experience"]:
        values += [entry["company"], entry["role"], entry["description"]]
    for entry in _FULL_CV["education"]:
        values += [
            entry["institution"],
            entry["degree"],
            entry["field_of_study"],
            entry["start_year"],
            entry["end_year"],
            entry["description"],
        ]
    for value in values:
        if value:
            assert value in text, value


def test_empty_full_name_falls_back_to_cv_name() -> None:
    text = convert(
        **_cv(
            name="Backend CV",
            personal_info={"full_name": "  ", "email": "a@b.c"},
            skills="Python",
        )
    )

    assert text == "# Backend CV\na@b.c\n\n## Skills\nPython"


def test_no_personal_info_uses_cv_name_heading() -> None:
    assert convert(**_cv(summary="Hi")) == "# My CV\n\n## Summary\nHi"


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"personal_info": {}, "work_experience": [], "education": []},
        {
            "personal_info": {"full_name": "", "email": None},
            "summary": "   ",
            "work_experience": [{"company": "", "role": "", "is_current": False}],
            "education": [{"institution": ""}],
            "skills": "",
            "languages": "\n",
        },
    ],
    ids=["all-null", "empty-containers", "blank-strings"],
)
def test_empty_cv_becomes_empty_text(fields: dict[str, Any]) -> None:
    assert convert(**_cv(**fields)) == ""


def test_only_full_name_gives_just_the_heading() -> None:
    assert convert(**_cv(personal_info={"full_name": "Jane"})) == "# Jane"


def test_contacts_are_joined_and_empty_ones_skipped() -> None:
    text = convert(
        **_cv(
            personal_info={
                "full_name": "Jane",
                "email": "",
                "phone": "+1",
                "location": None,
                "linkedin_url": "https://linkedin.com/in/j",
                "github_url": "https://github.com/j",
            }
        )
    )

    assert text == "# Jane\n+1 · https://linkedin.com/in/j · https://github.com/j"


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        (
            {
                "role": "Dev",
                "company": "X",
                "start_date": "2020-01",
                "end_date": "2021-07",
            },
            "### Dev — X\nJan 2020 – Jul 2021",
        ),
        (
            {"role": "Dev", "company": "X", "start_date": "2020-1", "is_current": True},
            "### Dev — X\nJan 2020 – Present",
        ),
        (
            {"role": "Dev", "company": "X", "is_current": True},
            "### Dev — X\nPresent",
        ),
        (
            {"role": "Dev", "company": "X", "start_date": "2020-05-17"},
            "### Dev — X\nMay 2020",
        ),
        (
            {"role": "Dev", "company": "X", "end_date": "2021-12"},
            "### Dev — X\nDec 2021",
        ),
        (
            {
                "role": "Dev",
                "company": "X",
                "start_date": "Spring 2020",
                "end_date": "2020-13",
            },
            "### Dev — X\nSpring 2020 – 2020-13",
        ),
        ({"role": "Dev", "company": ""}, "### Dev"),
        (
            {"role": "", "company": "X", "description": "Did things"},
            "### X\nDid things",
        ),
        ({"start_date": "2020", "description": "No title"}, "2020\nNo title"),
    ],
    ids=[
        "month-range",
        "current",
        "current-no-start",
        "full-date",
        "end-only",
        "raw-strings",
        "role-only",
        "company-only",
        "no-heading",
    ],
)
def test_experience_entry(entry: dict[str, Any], expected: str) -> None:
    assert (
        convert(**_cv(work_experience=[entry]))
        == f"# My CV\n\n## Experience\n{expected}"
    )


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ({"institution": "MIT", "degree": "BSc"}, "### BSc — MIT"),
        ({"institution": "MIT", "field_of_study": "CS"}, "### CS — MIT"),
        ({"institution": "MIT"}, "### MIT"),
        ({"institution": "MIT", "start_year": "2016"}, "### MIT\n2016"),
        ({"institution": "MIT", "end_year": "2020"}, "### MIT\n2020"),
    ],
    ids=["degree", "field-only", "institution-only", "start-only", "end-only"],
)
def test_education_entry(entry: dict[str, Any], expected: str) -> None:
    assert convert(**_cv(education=[entry])) == f"# My CV\n\n## Education\n{expected}"


def test_multiline_descriptions_are_kept() -> None:
    text = convert(
        **_cv(
            work_experience=[
                {"role": "Dev", "company": "X", "description": "  - Did A\n- Did B  "}
            ]
        )
    )

    assert text.endswith("### Dev — X\n- Did A\n- Did B")


def test_malformed_json_values_are_skipped() -> None:
    text = convert(
        **_cv(
            personal_info=["not", "a", "dict"],
            work_experience=["oops", {"role": "Dev", "company": "X"}],
            education={"institution": "MIT"},
            skills="Go",
        )
    )

    assert text == "# My CV\n\n## Experience\n### Dev — X\n\n## Skills\nGo"
