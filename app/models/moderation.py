from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Model
from app.models.base import utcnow

FLAG_REASONS = ("threat", "doxxing", "spam", "coordinated_harassment", "prohibited_material", "fabrication_suspected", "other")
FLAG_TARGETS = ("case", "publication", "conversation", "public_request", "user")
FLAG_STATUSES = ("open", "actioned", "dismissed")


class ModerationFlag(Model):
    __tablename__ = "moderation_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    raised_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    action_taken: Mapped[str | None] = mapped_column(Text, nullable=True)
    handled_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    raised_by = relationship("User", foreign_keys=[raised_by_id])
    handled_by = relationship("User", foreign_keys=[handled_by_id])
    appeals: Mapped[list[ModerationAppeal]] = relationship(back_populates="flag", cascade="all, delete-orphan")


class ModerationAppeal(Model):
    __tablename__ = "moderation_appeals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flag_id: Mapped[int] = mapped_column(ForeignKey("moderation_flags.id"), nullable=False, index=True)
    reference: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    flag: Mapped[ModerationFlag] = relationship(back_populates="appeals")
    decided_by = relationship("User")
