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
    dump = data.model_dump()
    # Serialize nested models to dicts for JSON columns
    if dump.get("personal_info"):
        dump["personal_info"] = data.personal_info.model_dump() if data.personal_info else None
    if dump.get("work_experience"):
        dump["work_experience"] = [e.model_dump() for e in data.work_experience] if data.work_experience else None
    if dump.get("education"):
        dump["education"] = [e.model_dump() for e in data.education] if data.education else None

    cv = Cv(user_id=user_id, **dump)
    db.add(cv)
    await db.commit()
    await db.refresh(cv)
    return cv


async def get_cv(db: AsyncSession, user_id: str, cv_id: str) -> Cv | None:
    result = await db.execute(
        select(Cv).where(Cv.id == cv_id, Cv.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_cv(
    db: AsyncSession, user_id: str, cv_id: str, data: CvUpdate
) -> Cv | None:
    cv = await get_cv(db, user_id, cv_id)
    if cv is None:
        return None

    update_data = data.model_dump(exclude_unset=True)

    # Serialize nested models for JSON columns
    if "personal_info" in update_data and data.personal_info:
        update_data["personal_info"] = data.personal_info.model_dump()
    if "work_experience" in update_data and data.work_experience:
        update_data["work_experience"] = [e.model_dump() for e in data.work_experience]
    if "education" in update_data and data.education:
        update_data["education"] = [e.model_dump() for e in data.education]

    for field, value in update_data.items():
        setattr(cv, field, value)

    await db.commit()
    await db.refresh(cv)
    return cv


async def delete_cv(db: AsyncSession, user_id: str, cv_id: str) -> bool:
    cv = await get_cv(db, user_id, cv_id)
    if cv is None:
        return False

    # SET NULL on linked applications
    result = await db.execute(
        select(Application).where(Application.cv_id == cv_id)
    )
    for app in result.scalars().all():
        app.cv_id = None

    await db.delete(cv)
    await db.commit()
    return True


async def duplicate_cv(
    db: AsyncSession, user_id: str, cv_id: str, new_name: str | None = None
) -> Cv | None:
    original = await get_cv(db, user_id, cv_id)
    if original is None:
        return None

    copy = Cv(
        user_id=user_id,
        name=new_name or f"{original.name} (copy)",
        personal_info=original.personal_info,
        summary=original.summary,
        work_experience=original.work_experience,
        education=original.education,
        skills=original.skills,
        languages=original.languages,
    )
    db.add(copy)
    await db.commit()
    await db.refresh(copy)
    return copy
