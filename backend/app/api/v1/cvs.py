from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.exceptions import not_found
from app.models.cv import Cv
from app.models.user import User
from app.schemas.cv import (
    CvCreate,
    CvDuplicateRequest,
    CvRead,
    CvTailoredFor,
    CvUpdate,
)
from app.services.cv_service import (
    CvDetails,
    CvVersionConflict,
    create_cv,
    delete_cv,
    describe_cv,
    duplicate_cv,
    get_cv,
    list_cvs,
    make_base,
    update_cv,
)

router = APIRouter(prefix="/cvs", tags=["cvs"])

# The frontend maps this code to "This CV was changed elsewhere ...".
CV_CHANGED_DETAIL = "CV_CHANGED"


def details_to_read(details: CvDetails) -> CvRead:
    """Build the CvRead response from a CV and its listed facts."""
    cv = details.cv
    target = details.tailored_for
    return CvRead(
        id=cv.id,
        name=cv.name,
        content=cv.content,
        kind=cv.kind,
        is_base=details.is_base,
        version=cv.version,
        tailored_for=(
            CvTailoredFor(
                application_id=target.application_id,
                company_name=target.company_name,
                role_title=target.role_title,
            )
            if target is not None
            else None
        ),
        tailored_application_deleted=details.tailored_application_deleted,
        linked_applications_count=details.linked_applications_count,
        created_at=cv.created_at,
        updated_at=cv.updated_at,
    )


async def cv_to_read(db: AsyncSession, user_id: str, cv: Cv) -> CvRead:
    return details_to_read(await describe_cv(db, user_id, cv))


@router.get("", response_model=list[CvRead])
async def list_user_cvs(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[CvRead]:
    """The base CV first, then other own CVs, then tailored copies; each group
    most recently updated first."""
    return [details_to_read(row) for row in await list_cvs(db, current_user.id)]


@router.post("", response_model=CvRead, status_code=status.HTTP_201_CREATED)
async def create_user_cv(
    body: CvCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CvRead:
    cv = await create_cv(db, current_user.id, body)
    return await cv_to_read(db, current_user.id, cv)


@router.get("/{cv_id}", response_model=CvRead)
async def get_user_cv(
    cv_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CvRead:
    cv = await get_cv(db, current_user.id, cv_id)
    if cv is None:
        not_found("CV")
    return await cv_to_read(db, current_user.id, cv)


@router.patch(
    "/{cv_id}",
    response_model=CvRead,
    responses={
        status.HTTP_409_CONFLICT: {
            "description": "`version` is stale: the CV was changed elsewhere "
            '(`{"detail": "CV_CHANGED"}`).'
        }
    },
)
async def update_user_cv(
    cv_id: str,
    body: CvUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CvRead:
    try:
        cv = await update_cv(db, current_user.id, cv_id, body)
    except CvVersionConflict:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=CV_CHANGED_DETAIL
        ) from None
    if cv is None:
        not_found("CV")
    return await cv_to_read(db, current_user.id, cv)


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


@router.post(
    "/{cv_id}/duplicate", response_model=CvRead, status_code=status.HTTP_201_CREATED
)
async def duplicate_user_cv(
    cv_id: str,
    body: CvDuplicateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CvRead:
    cv = await duplicate_cv(db, current_user.id, cv_id, body.name)
    if cv is None:
        not_found("CV")
    return await cv_to_read(db, current_user.id, cv)


@router.post(
    "/{cv_id}/make-base",
    response_model=CvRead,
    summary="Make this CV the user's base CV",
)
async def make_user_cv_base(
    cv_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CvRead:
    """Set the base CV ("Add & tailor CV" starts from it). The previous base
    becomes an ordinary own CV; a tailored copy becomes an own CV for good and
    keeps its application link. Idempotent."""
    cv = await make_base(db, current_user.id, cv_id)
    if cv is None:
        not_found("CV")
    return await cv_to_read(db, current_user.id, cv)
