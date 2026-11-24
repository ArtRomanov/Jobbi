"""add the pre-AI keyword filter

`vacancy_search_settings.keywords` (JSON list, default empty) and
`keyword_filter_enabled` (default true): a post reaches the AI only if it
names a keyword. An empty list lets every post through, so existing users see
no change until they add keywords. `vacancy_seen_keys.filtered_at`: when the
filter skipped the post (NULL otherwise).

Revision ID: b5d8f1a3c7e9
Revises: 9e2b4d6f8a10
Create Date: 2026-11-24 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5d8f1a3c7e9"
down_revision: str | None = "9e2b4d6f8a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("vacancy_search_settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "keywords", sa.JSON(), server_default=sa.text("'[]'"), nullable=False
            )
        )
        batch_op.add_column(
            sa.Column(
                "keyword_filter_enabled",
                sa.Boolean(),
                server_default=sa.true(),
                nullable=False,
            )
        )
    with op.batch_alter_table("vacancy_seen_keys", schema=None) as batch_op:
        batch_op.add_column(sa.Column("filtered_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("vacancy_seen_keys", schema=None) as batch_op:
        batch_op.drop_column("filtered_at")
    with op.batch_alter_table("vacancy_search_settings", schema=None) as batch_op:
        batch_op.drop_column("keyword_filter_enabled")
        batch_op.drop_column("keywords")
