from datetime import datetime

from pydantic import BaseModel


class ConnectionCodeResponse(BaseModel):
    code: str
    expires_at: datetime


class TelegramStatus(BaseModel):
    connected: bool
    telegram_username: str | None = None
    linked_at: datetime | None = None
