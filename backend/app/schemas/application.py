from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import DEFAULT_APPLICATION_STATUS

T = TypeVar("T")


class ApplicationCreate(BaseModel):
    company_name: str
    role_title: str
    job_url: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = Field(default=None, max_length=3)
    contact_name: str | None = None
    contact_email: str | None = None
    notes: str | None = None
    status: str = DEFAULT_APPLICATION_STATUS


class ApplicationUpdate(BaseModel):
    company_name: str | None = None
    role_title: str | None = None
    job_url: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = Field(default=None, max_length=3)
    contact_name: str | None = None
    contact_email: str | None = None
    notes: str | None = None
    status: str | None = None


class StatusHistoryRead(BaseModel):
    id: str
    status: str
    changed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplicationRead(BaseModel):
    id: str
    company_name: str
    role_title: str
    job_url: str | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    contact_name: str | None
    contact_email: str | None
    notes: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplicationDetailRead(ApplicationRead):
    status_history: list[StatusHistoryRead]


class StatusHistoryFeedRead(BaseModel):
    id: str
    application_id: str
    company_name: str
    role_title: str
    status: str
    changed_at: datetime


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    per_page: int