"""add forwarded posts

`forwarded_posts`: where to reply with the rating result of a post the user
forwarded to the bot, and whether that reply was sent (spec 012, 2.5).
Deleted by the daily cleanup 30 days after `created_at`.

Revision ID: a7c9e1b3d5f2
Revises: f1a3d5c7e9b2
Create Date: 2026-11-23 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c9e1b3d5f2"
down_revision: str | None = "f1a3d5c7e9b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "forwarded_posts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("external_key", sa.String(length=255), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("reported_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_forwarded_posts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_forwarded_posts")),
        sa.UniqueConstraint(
            "user_id",
            "external_key",
            name=op.f("uq_forwarded_posts_user_id_external_key"),
        ),
    )


def downgrade() -> None:
    op.drop_table("forwarded_posts")
