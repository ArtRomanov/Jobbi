from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.telegram import UtcDatetime

SourceKind = Literal["telegram", "greenhouse", "lever", "lever_eu"]


class VacancySourceCreate(BaseModel):
    # Length and shape are checked by the parser so the user gets a 400 with
    # a readable message instead of a 422 validation array.
    input: str


class VacancySourceRead(BaseModel):
    id: str
    # Stable identity "<kind>:<handle>" (survives remove / re-add); the Inbox
    # `source` filter takes it.
    key: str
    kind: SourceKind
    display_name: str
    last_checked_at: UtcDatetime | None
    scanning: bool
    unavailable: bool
    last_error: str | None


class VacancySearchSettingsRead(BaseModel):
    description: str | None = None
    exclude: list[str] = []


class VacancySearchSettingsUpdate(BaseModel):
    """Partial update: a field left out of the body stays unchanged.

    Types only. Limits and normalisation live in the service so the user gets
    a 400 with a readable message instead of a 422 validation array.
    """

    # Explicit null (or blank text) turns the search off.
    description: str | None = None
    exclude: list[str] = Field(default_factory=list)


class DiscoveryStatus(BaseModel):
    ai_unavailable: bool = False
    limit_reached: bool = False
    waiting_count: int = 0


class SourceRef(BaseModel):
    """A source as shown on a card or in the Inbox source filter."""

    key: str
    label: str


class VacancySourcesResponse(BaseModel):
    sources: list[VacancySourceRead]
    # Sources of Inbox cards that are no longer watched (shown "(removed)").
    removed_sources: list[SourceRef]
    settings: VacancySearchSettingsRead
    status: DiscoveryStatus


VacancyListState = Literal["new", "seen", "all"]
VacancySort = Literal["date", "fit"]


class ExistingApplicationRef(BaseModel):
    """An application already tracking the same job link."""

    id: str
    company_name: str
    role_title: str


class VacancyRead(BaseModel):
    id: str
    title: str | None
    company: str | None
    url: str
    job_link: str | None
    text: str
    posted_at: UtcDatetime
    found_at: UtcDatetime
    state: Literal["new", "seen"]
    fit: Literal["high", "medium", "low"] | None
    fit_reason: str | None
    # Sources the card came from (several for a merged repost).
    sources: list[SourceRef]
    # The user's application with the same normalized job link, if any.
    existing_application: ExistingApplicationRef | None = None


class NewVacancyCount(BaseModel):
    count: int


RequiredName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]


class AddToTrackerRequest(BaseModel):
    company_name: RequiredName
    role_title: RequiredName
    # Left out (or null): the card text becomes the notes.
    notes: str | None = None
    # "Add & tailor CV": copy this CV, name the copy and link it.
    base_cv_id: str | None = None
    # "Add anyway": skip the duplicate check.
    allow_duplicate: bool = False


class AddToTrackerResponse(BaseModel):
    application_id: str
    cv_id: str | None


class DuplicateApplicationDetail(BaseModel):
    message: Literal["You already track this"]
    application: ExistingApplicationRef


class DuplicateApplicationConflict(BaseModel):
    """409 body when the job link is already tracked (structured `detail`)."""

    detail: DuplicateApplicationDetail
