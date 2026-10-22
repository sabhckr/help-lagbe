"""Reason-gated access to the separate identity store. The only legitimate path to a name,
phone number or email address."""

from __future__ import annotations

from typing import Any

from app import permissions as P
from app.extensions import db
from app.models.base import utcnow
from app.models.case import Case
from app.services import access, audit


class IdentityAccessDenied(PermissionError):
    pass


def unlock(case: Case, user, reason: str, *, break_glass: bool = False) -> dict[str, Any]:
    """Return the decrypted identity payload for `case`, or raise.

    Requirements: the user holds case.identity_unlock (or case.break_glass for admins), can read the
    narrative (assigned / in triage), and gives a reason of at least 15 characters. Every call is
    logged with who, when, which case and why — including refused attempts."""
    reason = (reason or "").strip()
    if break_glass:
        allowed = user.can(P.CASE_BREAK_GLASS)
    else:
        allowed = user.can(P.CASE_IDENTITY_UNLOCK) and access.can_view_narrative(user, case)
    if not allowed or len(reason) < 15:
        audit.record(
            "identity.unlock_refused",
            actor=user,
            target_type="case",
            target_id=case.id,
            case_id=case.id,
            reason=reason or None,
            details={"break_glass": break_glass},
            commit=True,
        )
        raise IdentityAccessDenied("identity.error_denied")
    identity = case.identity
    if identity is None or identity.purged_at is not None:
        audit.record(
            "identity.unlock",
            actor=user,
            target_type="case",
            target_id=case.id,
            case_id=case.id,
            reason=reason,
            details={"break_glass": break_glass, "present": False},
            commit=True,
        )
        return {}
    payload = identity.read_payload()
    identity.access_count = (identity.access_count or 0) + 1
    identity.last_accessed_at = utcnow()
    audit.record(
        "identity.unlock",
        actor=user,
        target_type="case",
        target_id=case.id,
        case_id=case.id,
        reason=reason,
        details={"break_glass": break_glass, "present": True},
    )
    db.session.commit()
    return payload


def purge(case: Case, user, reason: str) -> None:
    identity = case.identity
    if identity is None:
        return
    identity.payload_enc = b""
    identity.purged_at = utcnow()
    audit.record("identity.purge", actor=user, target_type="case", target_id=case.id, case_id=case.id, reason=reason)
    db.session.commit()
