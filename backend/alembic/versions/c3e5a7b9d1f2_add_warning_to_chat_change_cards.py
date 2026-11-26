"""add warning to chat_change_cards

A CV change card can carry a warning (backlog #27): the edit breaks the CV
structure (a section removed or renamed, an entry heading or the header
lost) and the user did not ask for it. Existing cards get NULL.

Revision ID: c3e5a7b9d1f2
Revises: b5d8f1a3c7e9
Create Date: 2026-11-25 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3e5a7b9d1f2"
down_revision: str | None = "b5d8f1a3c7e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chat_change_cards", schema=None) as batch_op:
        batch_op.add_column(sa.Column("warning", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chat_change_cards", schema=None) as batch_op:
        batch_op.drop_column("warning")
