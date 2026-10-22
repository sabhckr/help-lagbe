from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.crypto import decrypt_json, encrypt_json
from app.extensions import Model
from app.models.base import utcnow

IDENTITY_FIELDS = ("name", "phone", "email", "safe_contact_notes", "do_not_contact", "safe_hours")


class ReporterIdentity(Model):
    """Reporter identity, stored apart from the case and encrypted at rest.

    Only reachable through services.identity.unlock(), which requires a permission, an
    assignment (or break-glass) and a written reason, and which writes an audit event.
    """

    __tablename__ = "reporter_identities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), unique=True, nullable=False)
    payload_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    case = relationship("Case", back_populates="identity")

    def set_payload(self, data: dict[str, Any]) -> None:
        clean = {k: (data.get(k) or "") for k in IDENTITY_FIELDS}
        self.payload_enc = encrypt_json(clean)

    def read_payload(self) -> dict[str, Any]:
        """Low-level decrypt. Callers must go through services.identity.unlock()."""
        return decrypt_json(self.payload_enc)

    def __repr__(self) -> str:
        return f"<ReporterIdentity case_id={self.case_id}>"
