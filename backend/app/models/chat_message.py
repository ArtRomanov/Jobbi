import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    application_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "user" or "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Set in Python with microseconds: the server default has 1-second
    # resolution on SQLite, and the order of messages decides which reply's
    # change cards can still be decided (the newest one only).
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<ChatMessage {self.role} @ {self.created_at}>"
