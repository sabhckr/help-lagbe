from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Model
from app.models.base import utcnow


class DepartmentConfig(Model):
    """Truthful availability per workspace. Nothing is shown as staffed unless an admin says
    it is, and live chat additionally requires an agent who is actually present."""

    __tablename__ = "department_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    department: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    is_staffed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_cases: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    hours_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    hours_bn: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notice_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    notice_bn: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    updated_by = relationship("User")


class EmergencyContact(Model):
    """External helplines. Shown publicly only when verified by a named staff member."""

    __tablename__ = "emergency_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # emergency | police | women_children | child | legal_aid | counselling | other
    name_en: Mapped[str] = mapped_column(String(120), nullable=False)
    name_bn: Mapped[str | None] = mapped_column(String(120), nullable=True)
    number: Mapped[str] = mapped_column(String(40), nullable=False)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_bn: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verification_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    verified_by = relationship("User")


class SiteSetting(Model):
    __tablename__ = "site_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
