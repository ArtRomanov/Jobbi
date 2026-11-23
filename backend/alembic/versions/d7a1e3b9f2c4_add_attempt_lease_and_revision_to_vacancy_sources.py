"""add initial_attempt_started_at and revision to vacancy_sources

Revision ID: d7a1e3b9f2c4
Revises: c4e9a2f7d1b3
Create Date: 2026-11-23 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7a1e3b9f2c4"
down_revision: str | None = "c4e9a2f7d1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("vacancy_sources", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("initial_attempt_started_at", sa.DateTime(), nullable=True)
        )
        # server_default fills existing rows with 0.
        batch_op.add_column(
            sa.Column(
                "revision",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("vacancy_sources", schema=None) as batch_op:
        batch_op.drop_column("revision")
        batch_op.drop_column("initial_attempt_started_at")
