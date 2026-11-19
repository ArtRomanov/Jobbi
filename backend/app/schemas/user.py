from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    timezone: str | None
    summary_time: str
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
    timezone: str | None = Field(default=None, max_length=64)
    # 24-hour HH:MM, 00:00–23:59
    summary_time: str | None = Field(
        default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$"
    )

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        """Accept only IANA names zoneinfo can resolve (same check the bot uses)."""
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown timezone: {value!r}") from exc
        return value


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
