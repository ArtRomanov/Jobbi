from datetime import datetime

from sqlalchemy import JSON, BigInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TelegramConversation(Base):
    __tablename__ = "telegram_conversations"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    step: Mapped[str] = mapped_column(String(32), nullable=False)
    context_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
