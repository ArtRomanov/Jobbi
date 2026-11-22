from typing import Literal

from pydantic import BaseModel

from app.schemas.telegram import UtcDatetime

SourceKind = Literal["telegram", "greenhouse", "lever", "lever_eu"]


class VacancySourceCreate(BaseModel):
    # Length and shape are checked by the parser so the user gets a 400 with
    # a readable message instead of a 422 validation array.
    input: str


class VacancySourceRead(BaseModel):
    id: str
    kind: SourceKind
    display_name: str
    last_checked_at: UtcDatetime | None
    scanning: bool
    unavailable: bool
    last_error: str | None


class VacancySearchSettingsRead(BaseModel):
    description: str | None = None
    exclude: list[str] = []


class DiscoveryStatus(BaseModel):
    ai_unavailable: bool = False
    limit_reached: bool = False
    waiting_count: int = 0


class VacancySourcesResponse(BaseModel):
    sources: list[VacancySourceRead]
    removed_labels: list[str]
    settings: VacancySearchSettingsRead
    status: DiscoveryStatus
