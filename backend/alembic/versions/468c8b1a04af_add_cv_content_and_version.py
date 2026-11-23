"""add cv content and version

Adds `cvs.content` (the whole CV as Markdown text) and `cvs.version` (the
optimistic-concurrency token), then converts every existing CV's structured
form fields into `content` (spec 011, functional spec 2.2).

The old structured columns are left untouched as the rollback path; downgrade
only drops the two new columns.

The converter below is a FROZEN copy: it must not import app code, so later
changes to the app cannot change what this migration did.

Revision ID: 468c8b1a04af
Revises: 031b22b73174
Create Date: 2026-11-23 12:00:00.000000

"""

import re
from collections.abc import Mapping, Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "468c8b1a04af"
down_revision: str | None = "031b22b73174"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Frozen converter: old form fields -> Markdown text (functional spec 2.2)
# ---------------------------------------------------------------------------

_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
_YEAR_MONTH_RE = re.compile(r"^(\d{4})-(\d{1,2})(?:-\d{1,2})?$")
_CONTACT_KEYS = ("email", "phone", "location", "linkedin_url")


def _text(value: Any) -> str:
    """Return a stripped string for any stored value; '' for None/non-text."""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, str | int | float):
        return str(value).strip()
    return ""


def _format_date(value: Any) -> str:
    """'2022-01' (or '2022-01-15') -> 'Jan 2022'; anything else stays as typed."""
    raw = _text(value)
    match = _YEAR_MONTH_RE.match(raw)
    if match is None:
        return raw
    month = int(match.group(2))
    if not 1 <= month <= 12:
        return raw
    return f"{_MONTHS[month - 1]} {match.group(1)}"


def _date_range(start: Any, end: Any, *, is_current: bool = False) -> str:
    start_text = _format_date(start)
    end_text = "Present" if is_current else _format_date(end)
    if start_text and end_text:
        return f"{start_text} – {end_text}"
    return start_text or end_text


def _heading(left: str, right: str) -> str:
    if left and right:
        return f"### {left} — {right}"
    return f"### {left or right}"


def _entry_block(heading_parts: tuple[str, str], dates: str, description: str) -> str:
    lines: list[str] = []
    if any(heading_parts):
        lines.append(_heading(*heading_parts))
    if dates:
        lines.append(dates)
    if description:
        lines.append(description)
    return "\n".join(lines)


def _experience_blocks(entries: Any) -> list[str]:
    if not isinstance(entries, list):
        return []
    blocks: list[str] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        block = _entry_block(
            (_text(entry.get("role")), _text(entry.get("company"))),
            _date_range(
                entry.get("start_date"),
                entry.get("end_date"),
                is_current=bool(entry.get("is_current")),
            ),
            _text(entry.get("description")),
        )
        if block:
            blocks.append(block)
    return blocks


def _education_blocks(entries: Any) -> list[str]:
    if not isinstance(entries, list):
        return []
    blocks: list[str] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        degree = " ".join(
            part
            for part in (_text(entry.get("degree")), _text(entry.get("field_of_study")))
            if part
        )
        block = _entry_block(
            (degree, _text(entry.get("institution"))),
            _date_range(entry.get("start_year"), entry.get("end_year")),
            _text(entry.get("description")),
        )
        if block:
            blocks.append(block)
    return blocks


def _contacts(personal_info: Mapping[str, Any]) -> list[str]:
    contacts = [_text(personal_info.get(key)) for key in _CONTACT_KEYS]
    # Any other stored personal-info value (e.g. other links) follows, in order.
    contacts.extend(
        _text(value)
        for key, value in personal_info.items()
        if key not in _CONTACT_KEYS and key != "full_name"
    )
    return [contact for contact in contacts if contact]


def convert_cv_to_text(
    *,
    name: str,
    personal_info: Any,
    summary: Any,
    work_experience: Any,
    education: Any,
    skills: Any,
    languages: Any,
) -> str:
    """Render one CV's old form fields as Markdown, leaving out empty parts.

    Returns '' when every form field is empty (the CV name alone is not content).
    """
    info: Mapping[str, Any] = (
        personal_info if isinstance(personal_info, Mapping) else {}
    )
    full_name = _text(info.get("full_name"))
    contacts = _contacts(info)

    sections: list[str] = []
    summary_text = _text(summary)
    if summary_text:
        sections.append(f"## Summary\n{summary_text}")
    experience = _experience_blocks(work_experience)
    if experience:
        sections.append("## Experience\n" + "\n\n".join(experience))
    degrees = _education_blocks(education)
    if degrees:
        sections.append("## Education\n" + "\n\n".join(degrees))
    skills_text = _text(skills)
    if skills_text:
        sections.append(f"## Skills\n{skills_text}")
    languages_text = _text(languages)
    if languages_text:
        sections.append(f"## Languages\n{languages_text}")

    if not (full_name or contacts or sections):
        return ""

    header = f"# {full_name or _text(name)}"
    if contacts:
        header += "\n" + " · ".join(contacts)
    return "\n\n".join([header, *sections])


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

_cvs = sa.table(
    "cvs",
    sa.column("id", sa.String),
    sa.column("name", sa.String),
    sa.column("personal_info", sa.JSON),
    sa.column("summary", sa.Text),
    sa.column("work_experience", sa.JSON),
    sa.column("education", sa.JSON),
    sa.column("skills", sa.Text),
    sa.column("languages", sa.Text),
    sa.column("content", sa.Text),
)


def upgrade() -> None:
    with op.batch_alter_table("cvs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "content", sa.Text(), server_default=sa.text("''"), nullable=False
            )
        )
        batch_op.add_column(
            sa.Column(
                "version", sa.Integer(), server_default=sa.text("1"), nullable=False
            )
        )

    bind = op.get_bind()
    rows = bind.execute(
        sa.select(
            _cvs.c.id,
            _cvs.c.name,
            _cvs.c.personal_info,
            _cvs.c.summary,
            _cvs.c.work_experience,
            _cvs.c.education,
            _cvs.c.skills,
            _cvs.c.languages,
        )
    ).all()
    for row in rows:
        content = convert_cv_to_text(
            name=row.name,
            personal_info=row.personal_info,
            summary=row.summary,
            work_experience=row.work_experience,
            education=row.education,
            skills=row.skills,
            languages=row.languages,
        )
        if content:
            bind.execute(
                sa.update(_cvs).where(_cvs.c.id == row.id).values(content=content)
            )


def downgrade() -> None:
    with op.batch_alter_table("cvs", schema=None) as batch_op:
        batch_op.drop_column("version")
        batch_op.drop_column("content")
