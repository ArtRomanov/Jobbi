"""add base cv and tailored copies

Adds the base-CV pointer `users.base_cv_id` and the tailored-copy columns
`cvs.kind` / `cvs.tailored_for_application_id` (spec 011, slices 5 and 6).

Data step (technical spec 2.1, migration step 3): a CV becomes a tailored
copy of an application when the application links it (`applications.cv_id`)
AND both rows were created within 5 seconds of each other ("Add & tailor CV"
creates them in one transaction). A CV linked by hand existed before its
application, so it never matches. The Inbox link is not required.
`users.base_cv_id` stays NULL for everyone (step 4).

The rule runs in Python over plain Core selects so it does not depend on any
database's date functions, and it does not import app code.

Revision ID: cd2779fea0d9
Revises: bc73545445d1
Create Date: 2026-11-23 16:08:33.614135

"""

from collections.abc import Sequence
from datetime import datetime, timedelta

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cd2779fea0d9"
down_revision: str | None = "bc73545445d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# "Add & tailor CV" writes the application and its CV copy in one transaction.
TAILORED_COPY_WINDOW = timedelta(seconds=5)

_cvs = sa.table(
    "cvs",
    sa.column("id", sa.String),
    sa.column("user_id", sa.String),
    sa.column("created_at", sa.DateTime),
    sa.column("kind", sa.String),
    sa.column("tailored_for_application_id", sa.String),
)

_applications = sa.table(
    "applications",
    sa.column("id", sa.String),
    sa.column("user_id", sa.String),
    sa.column("cv_id", sa.String),
    sa.column("created_at", sa.DateTime),
)


def find_tailored_copies(
    cvs: Sequence[tuple[str, str, datetime | None]],
    applications: Sequence[tuple[str, str, str | None, datetime | None]],
) -> dict[str, str]:
    """Map CV id -> application id for every CV that is a tailored copy.

    `cvs` rows are (id, user_id, created_at); `applications` rows are
    (id, user_id, cv_id, created_at). A CV matches an application of the same
    user that links it and was created within `TAILORED_COPY_WINDOW` of it.
    When several applications match one CV, the closest in time wins.
    """
    cv_by_id = {cv_id: (user_id, created_at) for cv_id, user_id, created_at in cvs}
    best: dict[str, tuple[timedelta, str]] = {}
    for app_id, app_user_id, cv_id, app_created_at in applications:
        if cv_id is None or cv_id not in cv_by_id:
            continue
        cv_user_id, cv_created_at = cv_by_id[cv_id]
        if cv_user_id != app_user_id or cv_created_at is None:
            continue
        if app_created_at is None:
            continue
        gap = abs(cv_created_at - app_created_at)
        if gap > TAILORED_COPY_WINDOW:
            continue
        if cv_id not in best or gap < best[cv_id][0]:
            best[cv_id] = (gap, app_id)
    return {cv_id: app_id for cv_id, (_gap, app_id) in best.items()}


def upgrade() -> None:
    with op.batch_alter_table("cvs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "kind", sa.String(length=10), server_default="own", nullable=False
            )
        )
        batch_op.add_column(
            sa.Column(
                "tailored_for_application_id", sa.String(length=36), nullable=True
            )
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_cvs_tailored_for_application_id_applications"),
            "applications",
            ["tailored_for_application_id"],
            ["id"],
            ondelete="SET NULL",
            use_alter=True,
        )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("base_cv_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_users_base_cv_id_cvs"),
            "cvs",
            ["base_cv_id"],
            ["id"],
            ondelete="SET NULL",
            use_alter=True,
        )

    bind = op.get_bind()
    cv_rows = bind.execute(
        sa.select(_cvs.c.id, _cvs.c.user_id, _cvs.c.created_at)
    ).all()
    app_rows = bind.execute(
        sa.select(
            _applications.c.id,
            _applications.c.user_id,
            _applications.c.cv_id,
            _applications.c.created_at,
        ).where(_applications.c.cv_id.is_not(None))
    ).all()
    for cv_id, app_id in find_tailored_copies(
        [tuple(row) for row in cv_rows], [tuple(row) for row in app_rows]
    ).items():
        bind.execute(
            sa.update(_cvs)
            .where(_cvs.c.id == cv_id)
            .values(kind="tailored", tailored_for_application_id=app_id)
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_users_base_cv_id_cvs"), type_="foreignkey"
        )
        batch_op.drop_column("base_cv_id")

    with op.batch_alter_table("cvs", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_cvs_tailored_for_application_id_applications"),
            type_="foreignkey",
        )
        batch_op.drop_column("tailored_for_application_id")
        batch_op.drop_column("kind")
