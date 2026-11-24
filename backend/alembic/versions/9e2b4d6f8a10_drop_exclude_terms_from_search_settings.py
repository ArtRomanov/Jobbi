"""drop exclude_terms from vacancy_search_settings

Exclude words are gone (backlog #12): spec 012 stopped applying and showing
them; the AI search description and the code rules decide instead. Stored
terms are dropped. A downgrade restores the column empty.

Revision ID: 9e2b4d6f8a10
Revises: d7a1e3b9f2c4
Create Date: 2026-11-24 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9e2b4d6f8a10"
down_revision: str | None = "d7a1e3b9f2c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("vacancy_search_settings", schema=None) as batch_op:
        batch_op.drop_column("exclude_terms")


def downgrade() -> None:
    with op.batch_alter_table("vacancy_search_settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "exclude_terms",
                sa.JSON(),
                server_default=sa.text("'[]'"),
                nullable=False,
            )
        )
