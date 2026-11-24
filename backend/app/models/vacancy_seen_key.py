import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VacancySeenKey(Base):
    """Permanent per-user memory of every post/job the discovery worker has seen.

    Never deleted by retention, so deleted cards never come back. ON DELETE
    CASCADE is declared for documentation and PostgreSQL; SQLite does not
    enforce it here (no PRAGMA foreign_keys), so user deletion must clear rows
    explicitly.
    """

    __tablename__ = "vacancy_seen_keys"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "external_key",
            name="uq_vacancy_seen_keys_user_id_external_key",
        ),
        # Daily-cap count: evaluated_at within the user's local day.
        Index("ix_vacancy_seen_keys_user_id_evaluated_at", "user_id", "evaluated_at"),
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
    # e.g. "tg:<channel>/<post_id>", "gh:<token>/<job_id>", "lever:<company>/<id>".
    external_key: Mapped[str] = mapped_column(String(255), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    # NULL if never sent to the AI (pre-filtered or older than the cutoff).
    evaluated_at: Mapped[datetime | None] = mapped_column()
    # The post was longer than the AI window (`MAX_POST_CHARS`) when it was
    # evaluated; counted by the daily summary's ✂️ line.
    cut_for_ai: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    # Skipped by the pre-AI keyword filter (never sent to the AI); counted by
    # the "skipped by the filter" line in the Sources panel.
    filtered_at: Mapped[datetime | None] = mapped_column()

    def __repr__(self) -> str:
        return f"<VacancySeenKey {self.external_key} user={self.user_id}>"
