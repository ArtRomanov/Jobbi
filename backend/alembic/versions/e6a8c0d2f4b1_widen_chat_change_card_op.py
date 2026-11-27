"""widen chat_change_cards.op for replace_all

A CV change card can now replace the whole CV (backlog #34): `op` takes
"replace_all", 11 characters, over the old VARCHAR(10). SQLite never enforced
the length, so existing rows and the live app work before this runs; the
column is widened so a database that does enforce it accepts the value.

Revision ID: e6a8c0d2f4b1
Revises: c3e5a7b9d1f2
Create Date: 2026-11-27 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6a8c0d2f4b1"
down_revision: str | None = "c3e5a7b9d1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chat_change_cards", schema=None) as batch_op:
        batch_op.alter_column(
            "op",
            existing_type=sa.String(length=10),
            type_=sa.String(length=16),
            existing_nullable=False,
        )


def downgrade() -> None:
    # A replace_all card does not fit the old column: those cards go first.
    op.execute("DELETE FROM chat_change_cards WHERE op = 'replace_all'")
    with op.batch_alter_table("chat_change_cards", schema=None) as batch_op:
        batch_op.alter_column(
            "op",
            existing_type=sa.String(length=16),
            type_=sa.String(length=10),
            existing_nullable=False,
        )
