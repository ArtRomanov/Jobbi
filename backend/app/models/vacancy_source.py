import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

VACANCY_SOURCE_KINDS = (
    "telegram",
    "greenhouse",
    "lever",
    "lever_eu",
    "teamtailor",
    "web",
)


class VacancySource(Base):
    """A watched Telegram channel, company job board or web listing page.

    ON DELETE CASCADE is declared for documentation and PostgreSQL; SQLite does
    not enforce it here (no PRAGMA foreign_keys), so delete paths must clear
    rows explicitly.
    """

    __tablename__ = "vacancy_sources"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "kind",
            "handle",
            name="uq_vacancy_sources_user_id_kind_handle",
        ),
        # NULL url_hash (non-web kinds) never collides on SQLite or PostgreSQL.
        UniqueConstraint(
            "user_id",
            "url_hash",
            name="uq_vacancy_sources_user_id_url_hash",
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
        index=True,
    )
    # One of VACANCY_SOURCE_KINDS.
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # Channel / board token / company slug, stored lowercased. For `web` the
    # handle is the source's own id: stable across link edits, so
    # vacancy_card_sources.source_handle and the ?source= key stay valid.
    handle: Mapped[str] = mapped_column(String(64), nullable=False)
    # Web only: normalized listing URL that is fetched.
    url: Mapped[str | None] = mapped_column(String(2048))
    # Web only: sha256 hex of `url`; backs the per-user duplicate check.
    url_hash: Mapped[str | None] = mapped_column(String(64))
    # Web only: optional substring a job link must contain.
    job_link_contains: Mapped[str | None] = mapped_column(String(100))
    # Name taken from the source itself: web domain, Telegram channel title or
    # job board title. Never the user's custom name.
    default_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Effective name shown everywhere: the user's custom name, else
    # default_name.
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    initial_scan_completed_at: Mapped[datetime | None] = mapped_column()
    next_initial_attempt_at: Mapped[datetime | None] = mapped_column()
    # Lease: set by the worker while a first-scan attempt runs, cleared when
    # it ends. Edits are refused while it is fresh; stale after 10 min
    # (crashed worker) and then ignored.
    initial_attempt_started_at: Mapped[datetime | None] = mapped_column()
    # Bumped by every edit that changes what is fetched. The worker stores
    # fetched results only if the revision is unchanged since it loaded it.
    revision: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default=text("0")
    )
    last_checked_at: Mapped[datetime | None] = mapped_column()
    failing_since: Mapped[datetime | None] = mapped_column()
    last_error: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<VacancySource {self.kind}:{self.handle} user={self.user_id}>"
