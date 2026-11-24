import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# pending = awaiting AI evaluation; the rest are visible/terminal card states.
VACANCY_STATES = ("pending", "new", "seen", "dismissed", "added")
VACANCY_FITS = ("high", "medium", "low")


class Vacancy(Base):
    """An Inbox card, or a post waiting for AI evaluation.

    Foreign keys declare ON DELETE SET NULL for documentation and PostgreSQL;
    SQLite does not enforce it here (no PRAGMA foreign_keys), so deleting a
    source or an application must clear source_id / application_id explicitly.
    """

    __tablename__ = "vacancies"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "external_key",
            name="uq_vacancies_user_id_external_key",
        ),
        Index("ix_vacancies_user_id_state_posted_at", "user_id", "state", "posted_at"),
        Index("ix_vacancies_user_id_job_link", "user_id", "job_link"),
        # Detail step: a web source's needs_detail rows, oldest first.
        Index(
            "ix_vacancies_source_id_needs_detail_found_at",
            "source_id",
            "needs_detail",
            "found_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    # Indexed via the composite indexes / unique constraint (user_id leads each).
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Source of the first post; NULL once that source is deleted.
    source_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("vacancy_sources.id", ondelete="SET NULL"),
    )
    external_key: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # Normalized URL of the actual job; merge key for reposts.
    job_link: Mapped[str | None] = mapped_column(String(2048))
    title: Mapped[str | None] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(255))
    # Plain text, at most 20 000 chars (enforced by the worker).
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Outside links of a pending post as `[line, url]` pairs (1-based line of
    # `text`), to pick each digest vacancy's job link (spec 012). NULL for rows
    # stored before spec 012, for board jobs and for cards made from a digest.
    links: Mapped[list[list[Any]] | None] = mapped_column(JSON)
    posted_at: Mapped[datetime] = mapped_column(nullable=False)
    found_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    # One of VACANCY_STATES.
    state: Mapped[str] = mapped_column(String(12), nullable=False)
    # One of VACANCY_FITS; NULL while pending.
    fit: Mapped[str | None] = mapped_column(String(8))
    fit_reason: Mapped[str | None] = mapped_column(String(255))
    eval_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    # Cards from a source's first scan are never alerted.
    from_initial_scan: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    # Web pending rows whose job page is not read yet; the evaluator skips them.
    needs_detail: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    # Failed job-page reads; at 3 the row is evaluated by its listing title.
    detail_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    alert_handled_at: Mapped[datetime | None] = mapped_column()
    application_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("applications.id", ondelete="SET NULL"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Vacancy {self.external_key} state={self.state} user={self.user_id}>"


class VacancyCardSource(Base):
    """Which sources a card came from; a merged repost adds a row.

    The Inbox source filter works on the source identity (kind + handle), so
    removed sources keep filtering. ON DELETE CASCADE (vacancy) / SET NULL (source) are declared for
    documentation and PostgreSQL; SQLite does not enforce them here.
    """

    __tablename__ = "vacancy_card_sources"
    __table_args__ = (
        UniqueConstraint(
            "vacancy_id",
            "source_kind",
            "source_handle",
            name="uq_vacancy_card_sources_vacancy_id_source_kind_source_handle",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    vacancy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("vacancies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("vacancy_sources.id", ondelete="SET NULL"),
    )
    # Source identity (VacancySource.kind + handle). The Inbox source filter
    # and "(removed)" use it, so a removed and re-added source (same kind and
    # handle, maybe a new title) keeps filtering its old cards.
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_handle: Mapped[str] = mapped_column(String(64), nullable=False)
    # Source display name at the time the card was found.
    label: Mapped[str] = mapped_column(String(255), nullable=False)

    def __repr__(self) -> str:
        return f"<VacancyCardSource {self.label} vacancy={self.vacancy_id}>"
