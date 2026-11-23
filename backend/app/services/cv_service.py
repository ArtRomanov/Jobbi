from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Select, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.cv import CV_KIND_OWN, CV_KIND_TAILORED, Cv
from app.models.user import User
from app.schemas.cv import CvCreate, CvUpdate
from app.services import chat_card_service


class CvNotFoundError(Exception):
    """No CV with this id belongs to the user."""


@dataclass(frozen=True, slots=True, kw_only=True)
class TailoredFor:
    """The application a tailored copy was made for."""

    application_id: str
    company_name: str
    role_title: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CvDetails:
    """A CV plus the facts the CV endpoints show next to it."""

    cv: Cv
    is_base: bool
    linked_applications_count: int
    # None for an own CV, and for a tailored copy whose application is gone.
    tailored_for: TailoredFor | None

    @property
    def tailored_application_deleted(self) -> bool:
        return self.cv.kind == CV_KIND_TAILORED and self.tailored_for is None


def _user_cv_ids(user_id: str) -> Select[tuple[str]]:
    """Subquery: ids of the user's CVs."""
    return select(Cv.id).where(Cv.user_id == user_id)


async def get_base_cv_id(db: AsyncSession, user_id: str) -> str | None:
    """The user's base CV id, or None. A pointer to a CV that no longer exists
    (SQLite does not enforce the FK) counts as "no base"."""
    return await db.scalar(
        select(User.base_cv_id).where(
            User.id == user_id, User.base_cv_id.in_(_user_cv_ids(user_id))
        )
    )


async def describe_cvs(
    db: AsyncSession, user_id: str, cvs: Sequence[Cv]
) -> list[CvDetails]:
    """Attach base flag, linked-application count and tailored target to the
    user's `cvs`, in the given order. Three queries whatever the count."""
    if not cvs:
        return []
    cv_ids = [cv.id for cv in cvs]
    base_cv_id = await get_base_cv_id(db, user_id)

    count_rows = await db.execute(
        select(Application.cv_id, func.count(Application.id))
        .where(Application.user_id == user_id, Application.cv_id.in_(cv_ids))
        .group_by(Application.cv_id)
    )
    counts: dict[str, int] = {cv_id: count for cv_id, count in count_rows}

    target_ids = {
        cv.tailored_for_application_id
        for cv in cvs
        if cv.tailored_for_application_id is not None
    }
    targets: dict[str, TailoredFor] = {}
    if target_ids:
        # Owner-scoped: another user's application is never described.
        rows = await db.execute(
            select(
                Application.id, Application.company_name, Application.role_title
            ).where(Application.user_id == user_id, Application.id.in_(target_ids))
        )
        targets = {
            app_id: TailoredFor(
                application_id=app_id, company_name=company, role_title=role
            )
            for app_id, company, role in rows
        }

    return [
        CvDetails(
            cv=cv,
            is_base=cv.id == base_cv_id,
            linked_applications_count=counts.get(cv.id, 0),
            tailored_for=(
                targets.get(cv.tailored_for_application_id)
                if cv.kind == CV_KIND_TAILORED and cv.tailored_for_application_id
                else None
            ),
        )
        for cv in cvs
    ]


async def describe_cv(db: AsyncSession, user_id: str, cv: Cv) -> CvDetails:
    return (await describe_cvs(db, user_id, [cv]))[0]


async def list_cvs(db: AsyncSession, user_id: str) -> list[CvDetails]:
    """The user's CVs: the base first, then the other own CVs, then tailored
    copies; each group most recently updated first."""
    base_cv_id = await get_base_cv_id(db, user_id)
    group = case(
        (Cv.id == (base_cv_id or ""), 0),
        (Cv.kind == CV_KIND_OWN, 1),
        else_=2,
    )
    result = await db.execute(
        select(Cv)
        .where(Cv.user_id == user_id)
        .order_by(group, Cv.updated_at.desc(), Cv.created_at.desc(), Cv.id)
    )
    return await describe_cvs(db, user_id, result.scalars().all())


async def create_cv(db: AsyncSession, user_id: str, data: CvCreate) -> Cv:
    cv = Cv(user_id=user_id, name=data.name, content=data.content)
    db.add(cv)
    await db.commit()
    await db.refresh(cv)
    return cv


async def create_uploaded_cv(
    db: AsyncSession, user_id: str, data: CvCreate
) -> tuple[Cv, bool]:
    """Create an own CV from an upload; it becomes the base if the user has
    none. Returns the CV and whether it became the base.

    The base is set by a conditional `UPDATE ... WHERE base_cv_id IS NULL OR
    base_cv_id NOT IN (the user's CVs)`, so of two concurrent first uploads
    only one becomes the base, and a dangling pointer counts as "no base".
    """
    cv = Cv(user_id=user_id, name=data.name, content=data.content)
    db.add(cv)
    await db.flush()
    result = await db.execute(
        update(User)
        .where(
            User.id == user_id,
            or_(
                User.base_cv_id.is_(None),
                User.base_cv_id.not_in(_user_cv_ids(user_id)),
            ),
        )
        .values(base_cv_id=cv.id)
        .execution_options(synchronize_session=False)
    )
    became_base = result.rowcount == 1
    await db.commit()
    await db.refresh(cv)
    return cv, became_base


async def make_base(db: AsyncSession, user_id: str, cv_id: str) -> Cv | None:
    """Make the user's CV `cv_id` their base CV. Returns None if it is not
    theirs. Idempotent.

    A tailored copy becomes an own CV for good and keeps its application link.
    Neither change touches `version` or `updated_at`.
    """
    cv = await get_cv(db, user_id, cv_id)
    if cv is None:
        return None
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(base_cv_id=cv.id)
        .execution_options(synchronize_session=False)
    )
    if cv.kind != CV_KIND_OWN:
        await db.execute(
            update(Cv)
            .where(Cv.id == cv.id)
            # Explicit so the `onupdate` does not move the CV in the list.
            .values(kind=CV_KIND_OWN, updated_at=Cv.updated_at)
            .execution_options(synchronize_session=False)
        )
    await db.commit()
    await db.refresh(cv)
    return cv


async def get_cv(db: AsyncSession, user_id: str, cv_id: str) -> Cv | None:
    result = await db.execute(select(Cv).where(Cv.id == cv_id, Cv.user_id == user_id))
    return result.scalar_one_or_none()


class CvVersionConflict(Exception):
    """The CV was changed since the caller read it (its version moved on)."""


async def update_cv_content_if_version(
    db: AsyncSession,
    user_id: str,
    cv_id: str,
    expected_version: int,
    *,
    name: str | None = None,
    content: str | None = None,
) -> Cv:
    """Write `name`/`content` only if the CV is still at `expected_version`.

    One conditional `UPDATE ... WHERE id AND user_id AND version`, so two
    writers racing on the same version cannot both win. Bumps `version` by one.
    `None` leaves a field unchanged. Does not commit: the caller owns the
    transaction (the chat card Accept commits its card state alongside).

    Raises CvNotFoundError if the CV is missing or another user's, and
    CvVersionConflict if it exists but is no longer at `expected_version`.
    """
    values: dict[str, object] = {"version": Cv.version + 1}
    if name is not None:
        values["name"] = name
    if content is not None:
        values["content"] = content

    result = await db.execute(
        update(Cv)
        .where(
            Cv.id == cv_id,
            Cv.user_id == user_id,
            Cv.version == expected_version,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        if await get_cv(db, user_id, cv_id) is None:
            raise CvNotFoundError(cv_id)
        raise CvVersionConflict(cv_id)

    fresh = await db.execute(
        select(Cv).where(Cv.id == cv_id).execution_options(populate_existing=True)
    )
    return fresh.scalar_one()


async def update_cv(
    db: AsyncSession, user_id: str, cv_id: str, data: CvUpdate
) -> Cv | None:
    """Apply an editor save. Returns None if the CV is not the user's.

    Raises CvVersionConflict if `data.version` is stale, also for a save that
    changes nothing. A save that changes nothing at the current version returns
    the CV without bumping its version.
    """
    cv = await get_cv(db, user_id, cv_id)
    if cv is None:
        return None
    if cv.version != data.version:
        raise CvVersionConflict(cv_id)

    # A null name/content means "unchanged".
    changes = data.model_dump(include={"name", "content"}, exclude_none=True)
    changed = {
        field: value for field, value in changes.items() if getattr(cv, field) != value
    }
    if not changed:
        return cv

    try:
        cv = await update_cv_content_if_version(
            db, user_id, cv_id, data.version, **changed
        )
    except CvNotFoundError:
        await db.rollback()
        return None
    except CvVersionConflict:
        await db.rollback()
        raise
    await db.commit()
    await db.refresh(cv)
    return cv


async def delete_cv(db: AsyncSession, user_id: str, cv_id: str) -> bool:
    cv = await get_cv(db, user_id, cv_id)
    if cv is None:
        return False

    # SET NULL on linked applications
    result = await db.execute(select(Application).where(Application.cv_id == cv_id))
    for app in result.scalars().all():
        app.cv_id = None
    # Cards keep `cv_id` without an FK: pending ones on this CV go stale.
    await chat_card_service.mark_cv_cards_stale(db, cv_id)
    # No FK enforcement on SQLite: deleting the base leaves no base.
    await db.execute(
        update(User)
        .where(User.id == user_id, User.base_cv_id == cv_id)
        .values(base_cv_id=None)
        .execution_options(synchronize_session=False)
    )

    await db.delete(cv)
    await db.commit()
    return True


async def build_cv_copy(
    db: AsyncSession,
    user_id: str,
    cv_id: str,
    name: str,
    *,
    tailored_for_application_id: str | None = None,
) -> Cv:
    """Add a copy of the user's CV `cv_id` under `name`, then flush.

    The copy is an own CV, or a tailored copy of the application
    `tailored_for_application_id` when given. It is never the base.
    Does not commit: the caller owns the transaction.

    Raises CvNotFoundError if the CV does not exist or is another user's.
    """
    original = await get_cv(db, user_id, cv_id)
    if original is None:
        raise CvNotFoundError(cv_id)

    copy = Cv(
        user_id=user_id,
        name=name,
        content=original.content,
        kind=CV_KIND_OWN if tailored_for_application_id is None else CV_KIND_TAILORED,
        tailored_for_application_id=tailored_for_application_id,
    )
    db.add(copy)
    await db.flush()
    return copy


async def duplicate_cv(
    db: AsyncSession, user_id: str, cv_id: str, new_name: str | None = None
) -> Cv | None:
    original = await get_cv(db, user_id, cv_id)
    if original is None:
        return None

    copy = await build_cv_copy(
        db, user_id, cv_id, new_name or f"{original.name} (copy)"
    )
    await db.commit()
    await db.refresh(copy)
    return copy
