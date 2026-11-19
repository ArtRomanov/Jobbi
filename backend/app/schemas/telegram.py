from datetime import datetime, timezone
from typing import Annotated, TypeAlias

from pydantic import AfterValidator, BaseModel


def _assume_utc(value: datetime) -> datetime:
    """DB timestamps are stored as naive UTC; attach the zone so JSON carries `Z`."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


UtcDatetime: TypeAlias = Annotated[datetime, AfterValidator(_assume_utc)]


class ConnectionCodeResponse(BaseModel):
    code: str
    expires_at: UtcDatetime


class TelegramStatus(BaseModel):
    connected: bool
    telegram_username: str | None = None
    linked_at: UtcDatetime | None = None
