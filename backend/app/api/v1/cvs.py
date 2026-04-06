from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.exceptions import not_found
from app.models.user import User
from app.schemas.cv import CvCreate, CvDuplicateRequest, CvRead, CvUpdate
from app.services.cv_service import (
    create_cv,
    delete_cv,
    duplicate_cv,
    get_cv,
    list_cvs,
    update_cv,
)

router = APIRouter(prefix="/cvs", tags=["cvs"])


def _cv_to_read(cv, linked_count: int = 0) -> CvRead:
    """Convert a Cv model to CvRead schema with linked application count."""
    return CvRead(
        id=cv.id,
        name=cv.name,
        personal_info=cv.personal_info,
        summary=cv.summary,
        work_experience=cv.work_experience,
        education=cv.education,
        skills=cv.skills,
        languages=cv.languages,
        linked_applications_count=linked_count,
        created_at=cv.created_at,
        updated_at=cv.updated_at,
    )


@router.get("", response_model=list[CvRead])
async def list_user_cvs(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[CvRead]:
    rows = await list_cvs(db, current_user.id)
    return [_cv_to_read(row["cv"], row["linked_applications_count"]) for row in rows]


@router.post("", response_model=CvRead, status_code=status.HTTP_201_CREATED)
async def create_user_cv(
    body: CvCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CvRead:
    cv = await create_cv(db, current_user.id, body)
    return _cv_to_read(cv)


@router.get("/{cv_id}", response_model=CvRead)
async def get_user_cv(
    cv_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CvRead:
    cv = await get_cv(db, current_user.id, cv_id)
    if cv is None:
        not_found("CV")
    return _cv_to_read(cv)


@router.patch("/{cv_id}", response_model=CvRead)
async def update_user_cv(
    cv_id: str,
    body: CvUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CvRead:
    cv = await update_cv(db, current_user.id, cv_id, body)
    if cv is None:
        not_found("CV")
    return _cv_to_read(cv)


@router.delete("/{cv_id}")
async def delete_user_cv(
    cv_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    deleted = await delete_cv(db, current_user.id, cv_id)
    if not deleted:
        not_found("CV")
    return {"message": "CV deleted."}


@router.post("/{cv_id}/duplicate", response_model=CvRead, status_code=status.HTTP_201_CREATED)
async def duplicate_user_cv(
    cv_id: str,
    body: CvDuplicateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CvRead:
    cv = await duplicate_cv(db, current_user.id, cv_id, body.name)
    if cv is None:
        not_found("CV")
    return _cv_to_read(cv)
