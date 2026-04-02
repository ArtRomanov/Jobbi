from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserRead(BaseModel):
    id: str
    email: str
    full_name: str
    desired_role: str | None
    desired_location: str | None
    remote_preference: str | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    full_name: str | None = None
    desired_role: str | None = None
    desired_location: str | None = None
    remote_preference: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = Field(default=None, max_length=3)
