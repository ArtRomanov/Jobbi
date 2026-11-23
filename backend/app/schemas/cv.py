from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

CV_CONTENT_MAX_CHARS = 20_000
CV_NAME_MAX_CHARS = 255

# Stripped before the length check, so a whitespace-only name is rejected.
CvName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=CV_NAME_MAX_CHARS
    ),
]
CvContent = Annotated[str, Field(max_length=CV_CONTENT_MAX_CHARS)]


class CvCreate(BaseModel):
    name: CvName
    content: CvContent = ""


class CvUpdate(BaseModel):
    name: CvName | None = None
    content: CvContent | None = None
    version: int


class CvTailoredFor(BaseModel):
    """The application a tailored copy was made for."""

    application_id: str
    company_name: str
    role_title: str


class CvRead(BaseModel):
    id: str
    name: str
    content: str
    kind: Literal["own", "tailored"]
    is_base: bool
    version: int
    # Set for a tailored copy whose application still exists.
    tailored_for: CvTailoredFor | None
    # A tailored copy whose application is gone ("Application deleted").
    tailored_application_deleted: bool
    linked_applications_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CvDuplicateRequest(BaseModel):
    name: str | None = None


class CvUploadRead(CvRead):
    """``POST /cvs/upload`` response: the new CV plus upload facts."""

    # The user had no base CV, so this upload became it.
    became_base: bool
    # The extracted text was over 20 000 characters and was cut.
    truncated: bool
