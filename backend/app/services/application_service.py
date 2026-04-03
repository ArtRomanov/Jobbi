from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.pagination import paginate
from app.models.application import Application, ApplicationStatusHistory
from app.schemas.application import ApplicationCreate, ApplicationUpdate


async def list_applications(
    db: AsyncSession,
    user_id: str,
    page: int = 1,
    per_page: int = 50,
    status: str | None = None,
    search: str | None = None,
) -> tuple[list[Application], int]:
    query = select(Application).where(Application.user_id == user_id)

    if status:
        query = query.where(Application.status == status)

    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                Application.company_name.ilike(pattern),
                Application.role_title.ilike(pattern),
            )
        )

    query = (
        query.options(selectinload(Application.status_history))
        .order_by(Application.updated_at.desc())
    )

    return await paginate(db, query, page, per_page)


async def create_application(
    db: AsyncSession,
    user_id: str,
    data: ApplicationCreate,
) -> Application:
    application = Application(
        user_id=user_id,
        **data.model_dump(),
    )
    db.add(application)
    await db.flush()

    # Auto-create initial status history entry
    history_entry = ApplicationStatusHistory(
        application_id=application.id,
        status=application.status,
    )
    db.add(history_entry)

    await db.commit()

    # Reload with status_history
    result = await db.execute(
        select(Application)
        .where(Application.id == application.id)
        .options(selectinload(Application.status_history))
    )
    return result.scalar_one()


async def get_application(
    db: AsyncSession,
    user_id: str,
    application_id: str,
) -> Application | None:
    result = await db.execute(
        select(Application)
        .where(Application.id == application_id, Application.user_id == user_id)
        .options(selectinload(Application.status_history))
    )
    return result.scalar_one_or_none()


async def update_application(
    db: AsyncSession,
    user_id: str,
    application_id: str,
    data: ApplicationUpdate,
) -> Application | None:
    application = await get_application(db, user_id, application_id)
    if application is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    old_status = application.status

    for field, value in update_data.items():
        setattr(application, field, value)

    # Auto-log status change
    new_status = update_data.get("status")
    if new_status and new_status != old_status:
        history_entry = ApplicationStatusHistory(
            application_id=application.id,
            status=new_status,
        )
        db.add(history_entry)

    await db.commit()

    # Reload with fresh status_history
    result = await db.execute(
        select(Application)
        .where(Application.id == application.id)
        .options(selectinload(Application.status_history))
    )
    return result.scalar_one()


async def delete_application(
    db: AsyncSession,
    user_id: str,
    application_id: str,
) -> bool:
    application = await get_application(db, user_id, application_id)
    if application is None:
        return False

    await db.delete(application)
    await db.commit()
    return True


async def get_status_history_feed(
    db: AsyncSession,
    user_id: str,
    page: int = 1,
    per_page: int = 50,
) -> tuple[list[dict], int]:
    base_query = (
        select(
            ApplicationStatusHistory.id,
            ApplicationStatusHistory.application_id,
            Application.company_name,
            Application.role_title,
            ApplicationStatusHistory.status,
            ApplicationStatusHistory.changed_at,
        )
        .join(Application, ApplicationStatusHistory.application_id == Application.id)
        .where(Application.user_id == user_id)
        .order_by(ApplicationStatusHistory.changed_at.desc())
    )

    rows, total = await paginate(db, base_query, page, per_page, scalars=False)

    items = [
        {
            "id": row.id,
            "application_id": row.application_id,
            "company_name": row.company_name,
            "role_title": row.role_title,
            "status": row.status,
            "changed_at": row.changed_at,
        }
        for row in rows
    ]

    return items, total