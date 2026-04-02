from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
