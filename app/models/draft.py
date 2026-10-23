"""Server-side reporting drafts. Answers and uploads are encrypted at rest and removed on submission."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Model
from app.models.base import utcnow

DRAFT_OPEN = "open"
DRAFT_SUBMITTING = "submitting"
DRAFT_SUBMITTED = "submitted"


class ReportDraft(Model):
    __tablename__ = "report_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=DRAFT_OPEN)
    payload_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    receipt_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    files: Mapped[list[DraftFile]] = relationship(back_populates="draft", cascade="all, delete-orphan", order_by="DraftFile.id")


class DraftFile(Model):
    __tablename__ = "report_draft_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("report_drafts.id"), nullable=False, index=True)
    stored_name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    draft: Mapped[ReportDraft] = relationship(back_populates="files")
