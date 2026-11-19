from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.timezones import is_valid_timezone


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
    # null clears the zone (the bot then uses UTC).
    timezone: str | None = Field(default=None, max_length=64)
    # 24-hour HH:MM, 00:00–23:59. Omit to keep the current value; null is
    # rejected because the column is NOT NULL. [0-9], not \d: \d also matches
    # non-ASCII digits such as "٠".
    summary_time: str | None = Field(
        default=None, pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$"
    )

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        """Accept only IANA names from the tz database (same check the bot uses)."""
        if value is None:
            return value
        if not is_valid_timezone(value):
            raise ValueError(f"Unknown timezone: {value!r}")
        return value

    @field_validator("summary_time")
    @classmethod
    def _reject_null_summary_time(cls, value: str | None) -> str | None:
        # Runs only for values the client sent, so an omitted field stays allowed.
        if value is None:
            raise ValueError("summary_time cannot be null")
        return value


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
