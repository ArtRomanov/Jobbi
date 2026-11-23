from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.cv import Cv
from app.schemas.cv import CvCreate, CvUpdate


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


async def update_cv(
    db: AsyncSession, user_id: str, cv_id: str, data: CvUpdate
) -> Cv | None:
    cv = await get_cv(db, user_id, cv_id)
    if cv is None:
        return None

    # `version` is accepted but not checked yet: the stale-version 409 lands in
    # spec 011 slice 3. A null name/content means "unchanged".
    changes = data.model_dump(include={"name", "content"}, exclude_none=True)
    changed = {
        field: value for field, value in changes.items() if getattr(cv, field) != value
    }
    if changed:
        for field, value in changed.items():
            setattr(cv, field, value)
        cv.version += 1
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

    await db.delete(cv)
    await db.commit()
    return True


class CvNotFoundError(Exception):
    """No CV with this id belongs to the user."""


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
