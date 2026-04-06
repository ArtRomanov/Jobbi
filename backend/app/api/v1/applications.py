from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.exceptions import not_found
from app.models.application import Application
from app.models.cv import Cv
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


async def _enrich_with_cv_name(db: AsyncSession, app: Application) -> dict:
    """Build a dict from the application model, adding cv_name if cv_id is set."""
    data = {c.key: getattr(app, c.key) for c in Application.__table__.columns}
    data["cv_name"] = None
    if app.cv_id:
        result = await db.execute(select(Cv.name).where(Cv.id == app.cv_id))
        data["cv_name"] = result.scalar_one_or_none()
    return data


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
    items = []
    for app in applications:
        enriched = await _enrich_with_cv_name(db, app)
        items.append(ApplicationRead(**enriched))
    return PaginatedResponse(
        items=items,
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
    enriched = await _enrich_with_cv_name(db, application)
    enriched["status_history"] = application.status_history
    return ApplicationDetailRead(**enriched)


@router.get("/{application_id}", response_model=ApplicationDetailRead)
async def get_app(
    application_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApplicationDetailRead:
    application = await get_application(db, current_user.id, application_id)
    if application is None:
        not_found("Application")
    enriched = await _enrich_with_cv_name(db, application)
    enriched["status_history"] = application.status_history
    return ApplicationDetailRead(**enriched)


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
        not_found("Application")
    enriched = await _enrich_with_cv_name(db, application)
    enriched["status_history"] = application.status_history
    return ApplicationDetailRead(**enriched)


@router.delete("/{application_id}")
async def delete_app(
    application_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    deleted = await delete_application(db, current_user.id, application_id)
    if not deleted:
        not_found("Application")
    return {"message": "Application deleted."}
