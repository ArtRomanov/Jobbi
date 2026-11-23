"""add detail columns to vacancies

Revision ID: b8d3f5a1c6e2
Revises: 4e7a1c9b2d05
Create Date: 2026-11-23 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8d3f5a1c6e2"
down_revision: str | None = "4e7a1c9b2d05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("vacancies", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "needs_detail", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch_op.add_column(
            sa.Column(
                "detail_attempts",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.create_index(
            "ix_vacancies_source_id_needs_detail_found_at",
            ["source_id", "needs_detail", "found_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("vacancies", schema=None) as batch_op:
        batch_op.drop_index("ix_vacancies_source_id_needs_detail_found_at")
        batch_op.drop_column("detail_attempts")
        batch_op.drop_column("needs_detail")
