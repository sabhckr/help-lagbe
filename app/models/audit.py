from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Model
from app.models.base import utcnow

# Event types that are "sensitive access" and are surfaced in the oversight views.
SENSITIVE_EVENTS = (
    "identity.unlock",
    "identity.purge",
    "evidence.download",
    "evidence.export",
    "case.break_glass",
    "support.supervisor_read",
    "audit.export",
    "auth.password_reset",
)


class AuditEvent(Model):
    """Append-only audit trail. Never stores narratives, identities or message bodies —
    only who, what, which record, when, and the stated reason."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"), nullable=True, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # short JSON, no PII
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)

    actor = relationship("User")
    case = relationship("Case")

    @property
    def is_sensitive(self) -> bool:
        return self.event_type in SENSITIVE_EVENTS
