"""add default_name to vacancy_sources

Revision ID: c4e9a2f7d1b3
Revises: b8d3f5a1c6e2
Create Date: 2026-11-23 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e9a2f7d1b3"
down_revision: str | None = "b8d3f5a1c6e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add as nullable so existing rows are accepted.
    with op.batch_alter_table("vacancy_sources", schema=None) as batch_op:
        batch_op.add_column(sa.Column("default_name", sa.String(length=255)))

    # 2. Backfill: existing sources have no custom names yet.
    op.execute("UPDATE vacancy_sources SET default_name = display_name")

    # 3. Tighten to NOT NULL.
    with op.batch_alter_table("vacancy_sources", schema=None) as batch_op:
        batch_op.alter_column(
            "default_name",
            existing_type=sa.String(length=255),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("vacancy_sources", schema=None) as batch_op:
        batch_op.drop_column("default_name")
