"""add links to vacancies

`vacancies.links`: the outside links of a pending post with the line each sits
on (a JSON list of `[line, url]`), used to pick a job link per vacancy of a
digest (spec 012, 2.1). Existing rows and board jobs keep NULL.

Revision ID: f1a3d5c7e9b2
Revises: e4b7c2a91f03
Create Date: 2026-11-23 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a3d5c7e9b2"
down_revision: str | None = "e4b7c2a91f03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("vacancies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("links", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("vacancies", schema=None) as batch_op:
        batch_op.drop_column("links")
