import re
from datetime import datetime
from typing import Annotated, Generic, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.core.constants import DEFAULT_APPLICATION_STATUS

T = TypeVar("T")

_ALLOWED_SCHEMES = frozenset({"http", "https"})
# A URL scheme as browsers read it: a letter, then letters/digits/"+-.", then ":".
_SCHEME_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*):")
# Browsers drop tab/CR/LF anywhere and leading C0 controls/spaces before parsing,
# so "java\tscript:" and " javascript:" still run as scripts.
_URL_IGNORED_RE = re.compile(r"[\t\n\r]")


def _check_job_url(value: str | None) -> str | None:
    """Allow empty, scheme-less text ("acme.com/jobs/1") or http(s) URLs.

    Any other scheme (javascript:, data:, vbscript:, file:, ...) is rejected,
    so a stored link can never run script or open local files when rendered.
    Note: "host:port/path" without "http://" reads as a scheme and is rejected.
    """
    if not value:
        return value
    probe = _URL_IGNORED_RE.sub("", value).lstrip("".join(map(chr, range(0x21))))
    match = _SCHEME_RE.match(probe)
    if match and match.group(1).lower() not in _ALLOWED_SCHEMES:
        raise ValueError("Job URL must start with http:// or https://.")
    return value


JobUrl = Annotated[str | None, AfterValidator(_check_job_url)]


class ApplicationCreate(BaseModel):
    company_name: str
    role_title: str
    job_url: JobUrl = None
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
    job_url: JobUrl = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = Field(default=None, max_length=3)
    contact_name: str | None = None
    contact_email: str | None = None
    notes: str | None = None
    status: str | None = None
    cv_id: str | None = None


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
    cv_id: str | None = None
    cv_name: str | None = None
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
