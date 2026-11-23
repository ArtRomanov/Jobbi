from datetime import datetime
from typing import Annotated

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


class CvRead(BaseModel):
    id: str
    name: str
    content: str
    version: int
    linked_applications_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CvDuplicateRequest(BaseModel):
    name: str | None = None
