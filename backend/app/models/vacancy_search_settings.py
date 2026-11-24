from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, ForeignKey, String, func, text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VacancySearchSettings(Base):
    """Per-user vacancy search preferences (one row per user).

    ON DELETE CASCADE is declared for documentation and PostgreSQL; SQLite does
    not enforce it here (no PRAGMA foreign_keys).
    """

    __tablename__ = "vacancy_search_settings"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # NULL means search is off.
    description: Mapped[str | None] = mapped_column(String(500))
    # Pre-AI keyword filter: lowercased keywords, at most 50. A post reaches
    # the AI only if it names one (see `discovery.keyword_filter`); applied
    # while `keyword_filter_enabled` and the list is not empty.
    keywords: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    keyword_filter_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    ai_failing_since: Mapped[datetime | None] = mapped_column()
    limit_reached_on: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<VacancySearchSettings user={self.user_id}>"
