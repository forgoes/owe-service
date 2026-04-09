from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    detected_language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    missing_fields_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    next_question: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
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

    messages = relationship(
        "ConversationMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    lead_profile = relationship(
        "LeadProfileRecord",
        back_populates="conversation",
        uselist=False,
        cascade="all, delete-orphan",
    )
    qualification_decision = relationship(
        "QualificationDecision",
        back_populates="conversation",
        uselist=False,
        cascade="all, delete-orphan",
    )
