"""add chat change cards

Adds `chat_change_cards`: CV text edits proposed by the chat assistant, each
accepted or rejected by the user (spec 011, slice 7). `cv_id` has no FK on
purpose: a deleted CV makes its pending cards stale.

Revision ID: bc73545445d1
Revises: 468c8b1a04af
Create Date: 2026-11-23 15:16:49.278525

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bc73545445d1"
down_revision: str | None = "468c8b1a04af"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_change_cards",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("application_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("cv_id", sa.String(length=36), nullable=False),
        sa.Column("op", sa.String(length=10), nullable=False),
        sa.Column("before_text", sa.Text(), nullable=False),
        sa.Column("after_text", sa.Text(), nullable=False),
        sa.Column("position", sa.String(length=10), nullable=True),
        sa.Column("anchor_text", sa.Text(), nullable=True),
        sa.Column(
            "state", sa.String(length=10), server_default="pending", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_chat_change_cards_application_id_applications"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["chat_messages.id"],
            name=op.f("fk_chat_change_cards_message_id_chat_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_change_cards")),
    )
    with op.batch_alter_table("chat_change_cards", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_chat_change_cards_application_id"),
            ["application_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("chat_change_cards", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chat_change_cards_application_id"))

    op.drop_table("chat_change_cards")
