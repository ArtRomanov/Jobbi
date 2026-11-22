from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.exceptions import not_found
from app.models.user import User
from app.models.vacancy_source import VacancySource
from app.schemas.vacancy import (
    DiscoveryStatus,
    VacancySearchSettingsRead,
    VacancySourceCreate,
    VacancySourceRead,
    VacancySourcesResponse,
)
from app.services.vacancy_source_check import SourceCheckError
from app.services.vacancy_source_parsing import SourceInputError
from app.services.vacancy_source_service import (
    DUPLICATE_SOURCE_MESSAGE,
    SOURCE_LIMIT_MESSAGE,
    DuplicateSourceError,
    SourceLimitError,
    add_source,
    delete_source,
    get_search_settings,
    is_scanning,
    is_unavailable,
    list_sources,
)

router = APIRouter(tags=["vacancies"])


def _source_to_read(source: VacancySource) -> VacancySourceRead:
    return VacancySourceRead(
        id=source.id,
        kind=source.kind,
        display_name=source.display_name,
        last_checked_at=source.last_checked_at,
        scanning=is_scanning(source),
        unavailable=is_unavailable(source),
        last_error=source.last_error,
    )


@router.get(
    "/vacancy-sources",
    response_model=VacancySourcesResponse,
    summary="List watched sources with search settings and status",
)
async def get_vacancy_sources(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VacancySourcesResponse:
    sources = await list_sources(db, current_user.id)
    settings_row = await get_search_settings(db, current_user.id)
    settings = (
        VacancySearchSettingsRead(
            description=settings_row.description,
            exclude=list(settings_row.exclude_terms),
        )
        if settings_row is not None
        else VacancySearchSettingsRead()
    )
    return VacancySourcesResponse(
        sources=[_source_to_read(s) for s in sources],
        # Filled once vacancy cards exist (Slice 3).
        removed_labels=[],
        settings=settings,
        # Computed from the worker's state in Slice 2/3.
        status=DiscoveryStatus(),
    )


@router.post(
    "/vacancy-sources",
    response_model=VacancySourceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a Telegram channel after checking it is public",
)
async def create_vacancy_source(
    body: VacancySourceCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VacancySourceRead:
    user_id = current_user.id
    try:
        source = await add_source(db, user_id, body.input)
    except (SourceInputError, SourceCheckError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    except SourceLimitError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=SOURCE_LIMIT_MESSAGE
        ) from exc
    except DuplicateSourceError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=DUPLICATE_SOURCE_MESSAGE
        ) from exc
    return _source_to_read(source)


@router.delete(
    "/vacancy-sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Stop watching a source",
)
async def delete_vacancy_source(
    source_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    if not await delete_source(db, current_user.id, source_id):
        not_found("Source")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
