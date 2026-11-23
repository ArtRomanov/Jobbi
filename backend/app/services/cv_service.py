from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.cv import Cv
from app.schemas.cv import CvCreate, CvUpdate
from app.services.chat_card_service import mark_cv_cards_stale


class CvNotFoundError(Exception):
    """No CV with this id belongs to the user."""


async def list_cvs(db: AsyncSession, user_id: str) -> list[dict]:
    """List all CVs for a user with linked application count."""
    # Subquery for linked application count
    count_subq = (
        select(
            Application.cv_id,
            func.count(Application.id).label("app_count"),
        )
        .where(Application.cv_id.isnot(None))
        .group_by(Application.cv_id)
        .subquery()
    )

    query = (
        select(Cv, func.coalesce(count_subq.c.app_count, 0).label("app_count"))
        .outerjoin(count_subq, Cv.id == count_subq.c.cv_id)
        .where(Cv.user_id == user_id)
        .order_by(Cv.updated_at.desc())
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "cv": row[0],
            "linked_applications_count": row[1],
        }
        for row in rows
    ]


async def create_cv(db: AsyncSession, user_id: str, data: CvCreate) -> Cv:
    cv = Cv(user_id=user_id, name=data.name, content=data.content)
    db.add(cv)
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
    await mark_cv_cards_stale(db, cv_id)

    await db.delete(cv)
    await db.commit()
    return True


async def build_cv_copy(db: AsyncSession, user_id: str, cv_id: str, name: str) -> Cv:
    """Add a copy of the user's CV `cv_id` under `name`, then flush.

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
