import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ForwardedPost(Base):
    """A post the user forwarded to the bot: where to reply with its rating
    result (spec 012, 2.2) and whether that reply was sent.

    `reported_at` stays NULL until the result reply was attempted (also set
    when Telegram refused it). Deleted by the daily cleanup 30 days after
    `created_at`. ON DELETE CASCADE is declared for documentation and
    PostgreSQL; SQLite does not enforce it here (no PRAGMA foreign_keys), so
    user deletion must clear rows explicitly (like `vacancy_seen_keys`).
    """

    __tablename__ = "forwarded_posts"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "external_key",
            name="uq_forwarded_posts_user_id_external_key",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The post's seen key, e.g. "tgc:<internal id>/<post id>".
    external_key: Mapped[str] = mapped_column(String(255), nullable=False)
    # The user's private chat with the bot and the forwarded message in it.
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    reported_at: Mapped[datetime | None] = mapped_column()

    def __repr__(self) -> str:
        return f"<ForwardedPost {self.external_key} user={self.user_id}>"
