from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class LeadProfileRecord(Base):
    __tablename__ = "lead_profiles"

    conversation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("conversations.session_id", ondelete="CASCADE"),
        primary_key=True,
    )
    business_segment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    annual_usage_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    usage_estimated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    square_footage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contract_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    contract_expiry_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    building_age_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_current_provider: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    notes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    conversation = relationship("Conversation", back_populates="lead_profile")
