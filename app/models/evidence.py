from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Model
from app.models.base import utcnow

SCAN_CLEAN = "clean"
SCAN_INFECTED = "infected"
SCAN_NOT_SCANNED = "not_scanned"
SCAN_ERROR = "error"
SCAN_PENDING = "pending"


class Evidence(Model):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    stored_name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Encrypted contents. Deferred so lists of evidence never load file data. NULL for older records kept on disk.
    data_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scan_status: Mapped[str] = mapped_column(String(16), nullable=False, default=SCAN_NOT_SCANNED)
    scan_detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uploaded_by_reporter: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    uploaded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    quarantined: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    case = relationship("Case", back_populates="evidence")
    uploaded_by = relationship("User")
    custody: Mapped[list[CustodyRecord]] = relationship(
        back_populates="evidence", cascade="all, delete-orphan", order_by="CustodyRecord.created_at"
    )

    @property
    def is_available(self) -> bool:
        return self.deleted_at is None and not self.quarantined


class CustodyRecord(Model):
    """Chain of custody for evidence: every receipt, hash verification, access, export, transfer."""

    __tablename__ = "evidence_custody"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"), nullable=False, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # received|hash_verified|accessed|exported|preserved|transferred|quarantined
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    hash_at_time: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    evidence: Mapped[Evidence] = relationship(back_populates="custody")
    actor = relationship("User")
