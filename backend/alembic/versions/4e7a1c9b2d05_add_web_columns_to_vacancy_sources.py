"""add web columns to vacancy_sources

Revision ID: 4e7a1c9b2d05
Revises: cd2779fea0d9
Create Date: 2026-11-23 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4e7a1c9b2d05"
down_revision: str | None = "cd2779fea0d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("vacancy_sources", schema=None) as batch_op:
        batch_op.add_column(sa.Column("url", sa.String(length=2048), nullable=True))
        batch_op.add_column(
            sa.Column("url_hash", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("job_link_contains", sa.String(length=100), nullable=True)
        )
        batch_op.create_unique_constraint(
            batch_op.f("uq_vacancy_sources_user_id_url_hash"),
            ["user_id", "url_hash"],
        )


def downgrade() -> None:
    with op.batch_alter_table("vacancy_sources", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("uq_vacancy_sources_user_id_url_hash"), type_="unique"
        )
        batch_op.drop_column("job_link_contains")
        batch_op.drop_column("url_hash")
        batch_op.drop_column("url")
