import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)

    desired_role: Mapped[str | None] = mapped_column(String(255))
    desired_location: Mapped[str | None] = mapped_column(String(255))
    remote_preference: Mapped[str | None] = mapped_column(String(20))
    salary_min: Mapped[int | None] = mapped_column()
    salary_max: Mapped[int | None] = mapped_column()
    salary_currency: Mapped[str | None] = mapped_column(String(3))

    timezone: Mapped[str | None] = mapped_column(String(64))
    summary_time: Mapped[str] = mapped_column(
        String(5), nullable=False, default="10:00", server_default="10:00"
    )

    # The user's base CV: "Add & tailor CV" starts from it. At most one per
    # user by construction. SQLite does not enforce FKs, so `delete_cv` nulls
    # it by hand. `use_alter` breaks the users <-> cvs FK cycle.
    base_cv_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("cvs.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"
