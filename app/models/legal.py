from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Model
from app.models.base import utcnow

LEGAL_STATUSES = ("intake", "qualified_review", "referred", "awaiting_client", "closed")


class LegalIntake(Model):
    __tablename__ = "legal_intakes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), unique=True, nullable=False)
    opened_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    matter_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="intake")
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    referral_partner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    qualified_reviewer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    case = relationship("Case", back_populates="legal_intake")
    opened_by = relationship("User")
