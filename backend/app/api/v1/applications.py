from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.application import (
    ApplicationCreate,
    ApplicationDetailRead,
    ApplicationRead,
    ApplicationUpdate,
    PaginatedResponse,
    StatusHistoryFeedRead,
)
from app.services.application_service import (
    create_application,
    delete_application,
    get_application,
    get_status_history_feed,
    list_applications,
    update_application,
)

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("", response_model=PaginatedResponse[ApplicationRead])
async def list_apps(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
) -> PaginatedResponse[ApplicationRead]:
    applications, total = await list_applications(
        db, current_user.id, page, per_page, status_filter, search
    )
    return PaginatedResponse(
        items=[ApplicationRead.model_validate(app) for app in applications],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/history", response_model=PaginatedResponse[StatusHistoryFeedRead])
async def history_feed(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
) -> PaginatedResponse[StatusHistoryFeedRead]:
    items, total = await get_status_history_feed(
        db, current_user.id, page, per_page
    )
    return PaginatedResponse(
        items=[StatusHistoryFeedRead(**item) for item in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("", response_model=ApplicationDetailRead, status_code=status.HTTP_201_CREATED)
async def create_app(
    body: ApplicationCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApplicationDetailRead:
    application = await create_application(db, current_user.id, body)
    return ApplicationDetailRead.model_validate(application)


@router.get("/{application_id}", response_model=ApplicationDetailRead)
async def get_app(
    application_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApplicationDetailRead:
    application = await get_application(db, current_user.id, application_id)
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )
    return ApplicationDetailRead.model_validate(application)


@router.patch("/{application_id}", response_model=ApplicationDetailRead)
async def update_app(
    application_id: str,
    body: ApplicationUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApplicationDetailRead:
    application = await update_application(
        db, current_user.id, application_id, body
    )
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )
    return ApplicationDetailRead.model_validate(application)


@router.delete("/{application_id}")
async def delete_app(
    application_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    deleted = await delete_application(db, current_user.id, application_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )
    return {"message": "Application deleted."}