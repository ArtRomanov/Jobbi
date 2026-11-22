from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.exceptions import not_found
from app.models.user import User
from app.models.vacancy_search_settings import VacancySearchSettings
from app.models.vacancy_source import VacancySource
from app.schemas.application import PaginatedResponse
from app.schemas.vacancy import (
    DiscoveryStatus,
    NewVacancyCount,
    SourceRef,
    VacancyListState,
    VacancyRead,
    VacancySearchSettingsRead,
    VacancySearchSettingsUpdate,
    VacancySort,
    VacancySourceCreate,
    VacancySourceRead,
    VacancySourcesResponse,
)
from app.services.vacancy_service import (
    VacancyNotFoundError,
    VacancyNotInInboxError,
    count_new,
    discovery_status,
    dismiss_vacancy,
    list_vacancies,
    mark_seen,
    removed_sources,
    restore_vacancy,
    source_key,
)
from app.services.vacancy_source_check import SourceCheckError
from app.services.vacancy_source_parsing import SourceInputError
from app.services.vacancy_source_service import (
    DUPLICATE_SOURCE_MESSAGE,
    SOURCE_LIMIT_MESSAGE,
    UNSET,
    DuplicateSourceError,
    SearchSettingsError,
    SourceLimitError,
    add_source,
    delete_source,
    get_search_settings,
    is_scanning,
    is_unavailable,
    list_sources,
    update_search_settings,
)

router = APIRouter(tags=["vacancies"])

NOT_IN_INBOX_MESSAGE = "Vacancy is not in the Inbox."

CardAction = Callable[[AsyncSession, str, str], Awaitable[None]]


def _source_to_read(source: VacancySource) -> VacancySourceRead:
    return VacancySourceRead(
        id=source.id,
        key=source_key(source.kind, source.handle),
        kind=source.kind,
        display_name=source.display_name,
        last_checked_at=source.last_checked_at,
        scanning=is_scanning(source),
        unavailable=is_unavailable(source),
        last_error=source.last_error,
    )


def _settings_to_read(
    settings_row: VacancySearchSettings | None,
) -> VacancySearchSettingsRead:
    if settings_row is None:
        return VacancySearchSettingsRead()
    return VacancySearchSettingsRead(
        description=settings_row.description,
        exclude=list(settings_row.exclude_terms),
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
    status_data = await discovery_status(db, current_user, settings_row)
    return VacancySourcesResponse(
        sources=[_source_to_read(s) for s in sources],
        removed_sources=[
            SourceRef(key=item.key, label=item.label)
            for item in await removed_sources(db, current_user.id)
        ],
        settings=_settings_to_read(settings_row),
        status=DiscoveryStatus(
            ai_unavailable=status_data.ai_unavailable,
            limit_reached=status_data.limit_reached,
            waiting_count=status_data.waiting_count,
        ),
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


@router.patch(
    "/vacancy-search-settings",
    response_model=VacancySearchSettingsRead,
    summary="Update the search description and exclude words",
    description=(
        "Partial update: fields left out stay unchanged. A null or blank "
        "description turns the search off. Exclude words are trimmed, "
        "lowercased and de-duplicated. 400 when a limit is exceeded."
    ),
)
async def patch_vacancy_search_settings(
    body: VacancySearchSettingsUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VacancySearchSettingsRead:
    fields = body.model_fields_set
    try:
        settings_row = await update_search_settings(
            db,
            current_user.id,
            description=body.description if "description" in fields else UNSET,
            exclude=body.exclude if "exclude" in fields else UNSET,
        )
    except SearchSettingsError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    return _settings_to_read(settings_row)


@router.get(
    "/vacancies",
    response_model=PaginatedResponse[VacancyRead],
    summary="List Inbox cards",
    description=(
        "Only `new` and `seen` cards are listed. `source` filters by source "
        "key `<kind>:<handle>` (removed sources keep their key). `sort=fit` orders High, "
        "Medium, Low, newest first within the same fit."
    ),
)
async def get_vacancies(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source: Annotated[
        str | None,
        Query(
            max_length=128,
            description='Source key "<kind>:<handle>" (live or removed source)',
        ),
    ] = None,
    state: VacancyListState = "all",
    sort: VacancySort = "date",
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedResponse[VacancyRead]:
    items, card_sources, total = await list_vacancies(
        db,
        current_user.id,
        source=source,
        state=state,
        sort=sort,
        page=page,
        per_page=per_page,
    )
    return PaginatedResponse(
        items=[
            VacancyRead(
                id=v.id,
                title=v.title,
                company=v.company,
                url=v.url,
                job_link=v.job_link,
                text=v.text,
                posted_at=v.posted_at,
                found_at=v.found_at,
                state=v.state,  # type: ignore[arg-type]  # filtered to new/seen
                fit=v.fit,  # type: ignore[arg-type]
                fit_reason=v.fit_reason,
                sources=[
                    SourceRef(key=item.key, label=item.label)
                    for item in card_sources.get(v.id, [])
                ],
            )
            for v in items
        ],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/vacancies/new-count",
    response_model=NewVacancyCount,
    summary="Number of new Inbox cards (nav badge)",
)
async def get_new_vacancy_count(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NewVacancyCount:
    return NewVacancyCount(count=await count_new(db, current_user.id))


async def _run_card_action(
    action: CardAction, db: AsyncSession, user_id: str, vacancy_id: str
) -> Response:
    try:
        await action(db, user_id, vacancy_id)
    except VacancyNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Vacancy not found."
        ) from exc
    except VacancyNotInInboxError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=NOT_IN_INBOX_MESSAGE
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


_CARD_ACTION_RESPONSES: dict[int | str, dict[str, str]] = {
    404: {"description": "No such card for this user, or still awaiting the AI"},
    409: {"description": "The card has left the Inbox"},
}


@router.post(
    "/vacancies/{vacancy_id}/seen",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=_CARD_ACTION_RESPONSES,
    summary="Mark a card as seen (Open source)",
    description="`new → seen`; repeating on a seen card is a no-op. "
    "409 for dismissed or added cards.",
)
async def post_vacancy_seen(
    vacancy_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    return await _run_card_action(mark_seen, db, current_user.id, vacancy_id)


@router.post(
    "/vacancies/{vacancy_id}/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=_CARD_ACTION_RESPONSES,
    summary="Dismiss a card",
    description="`new|seen → dismissed`; repeating is a no-op. 409 for added cards.",
)
async def post_vacancy_dismiss(
    vacancy_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    return await _run_card_action(dismiss_vacancy, db, current_user.id, vacancy_id)


@router.post(
    "/vacancies/{vacancy_id}/restore",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=_CARD_ACTION_RESPONSES,
    summary="Undo a dismiss: the card returns as seen",
    description="`dismissed → seen`; a card already in the Inbox (new/seen) "
    "is left unchanged. 409 for added cards.",
)
async def post_vacancy_restore(
    vacancy_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    return await _run_card_action(restore_vacancy, db, current_user.id, vacancy_id)
