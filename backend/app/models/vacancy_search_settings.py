from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, String, func
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
    ai_failing_since: Mapped[datetime | None] = mapped_column()
    limit_reached_on: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<VacancySearchSettings user={self.user_id}>"
