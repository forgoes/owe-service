from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class QualificationDecision(Base):
    __tablename__ = "qualification_decisions"

    conversation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("conversations.session_id", ondelete="CASCADE"),
        primary_key=True,
    )
    tier: Mapped[str] = mapped_column(String(32), nullable=False, default="unqualified")
    bucket: Mapped[str] = mapped_column(String(16), nullable=False, default="lemon")
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    conversation = relationship("Conversation", back_populates="qualification_decision")
