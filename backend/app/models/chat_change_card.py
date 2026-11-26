import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

CARD_OPS = ("replace", "insert", "remove")
CARD_POSITIONS = ("start", "end", "after_line")
CARD_STATES = ("pending", "accepted", "rejected", "stale")


class ChatChangeCard(Base):
    """One CV text edit proposed by the assistant (spec 011, functional 2.7).

    SQLite does not enforce the foreign keys here (no PRAGMA foreign_keys), so
    clearing the chat and deleting the application delete these rows by hand.
    `cv_id` has no FK on purpose: a deleted CV makes the card stale.
    """

    __tablename__ = "chat_change_cards"

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
    message_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    cv_id: Mapped[str] = mapped_column(String(36), nullable=False)
    op: Mapped[str] = mapped_column(String(10), nullable=False)
    before_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    after_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Insert only: start / end / after_line.
    position: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Insert after a line: the quoted line the new text goes after.
    anchor_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Shown on the card: the edit breaks the CV structure (a section gone or
    # renamed, an entry heading or the header lost) and the user did not ask.
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(
        String(10), nullable=False, default="pending", server_default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)

    def __repr__(self) -> str:
        return f"<ChatChangeCard {self.op} {self.state}>"
