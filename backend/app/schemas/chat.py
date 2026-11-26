from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

CardOp = Literal["replace", "insert", "remove"]
CardPosition = Literal["start", "end", "after_line"]
CardState = Literal["pending", "accepted", "rejected", "stale"]


class ChatRequest(BaseModel):
    content: str


class ChangeCardRead(BaseModel):
    """A CV text edit proposed by the assistant (spec 011, functional 2.7)."""

    id: str
    message_id: str
    cv_id: str
    op: CardOp
    before_text: str
    after_text: str
    position: CardPosition | None
    anchor_text: str | None
    # Set when the edit breaks the CV structure the user did not ask to change
    # ("This change removes the CERTIFICATIONS section."); null otherwise.
    warning: str | None
    state: CardState
    created_at: datetime
    decided_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ChatMessageRead(BaseModel):
    id: str
    application_id: str
    role: str
    content: str
    created_at: datetime
    # The CV change cards this assistant message proposed; [] for user messages.
    cards: list[ChangeCardRead] = []

    model_config = ConfigDict(from_attributes=True)
