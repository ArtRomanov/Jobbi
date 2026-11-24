"""add cut_for_ai to vacancy_seen_keys

`vacancy_seen_keys.cut_for_ai`: set when an evaluated post was longer than the
AI window (3,000 characters); the daily summary counts these (spec 012, 2.6).
Existing rows get false.

Revision ID: e4b7c2a91f03
Revises: cd2779fea0d9
Create Date: 2026-11-23 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4b7c2a91f03"
down_revision: str | None = "cd2779fea0d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("vacancy_seen_keys", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "cut_for_ai", sa.Boolean(), server_default=sa.false(), nullable=False
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("vacancy_seen_keys", schema=None) as batch_op:
        batch_op.drop_column("cut_for_ai")
