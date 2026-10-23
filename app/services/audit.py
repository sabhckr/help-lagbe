"""Append-only audit trail. Call record() for every sensitive action."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from flask import current_app, has_request_context, request

from app.extensions import db
from app.models.audit import AuditEvent

log = logging.getLogger("helplagbe.audit")


def _ip_hash() -> str | None:
    if not has_request_context():
        return None
    addr = request.remote_addr or ""
    if not addr:
        return None
    salt = current_app.config["SECRET_KEY"]
    return hashlib.sha256(f"{salt}:{addr}".encode()).hexdigest()[:32]


def record(
    event_type: str,
    *,
    actor=None,
    target_type: str | None = None,
    target_id: int | None = None,
    case_id: int | None = None,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
    commit: bool = False,
) -> AuditEvent:
    """Write an audit event. `details` must never contain narratives, identities or message bodies.

    A hashed IP is kept only for staff actions and sign-in attempts. Anonymous reporting and tracking events
    carry no IP link, so an anonymous report cannot be tied back to a connection through the audit trail.
    """
    event = AuditEvent(
        actor_id=getattr(actor, "id", None),
        actor_role=getattr(actor, "role", None),
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        case_id=case_id,
        reason=(reason or None),
        details=json.dumps(details, ensure_ascii=False)[:2000] if details else None,
        ip_hash=_ip_hash() if (actor is not None or event_type.startswith("auth.")) else None,
    )
    db.session.add(event)
    if commit:
        db.session.commit()
    # Structured application log line without PII.
    log.info("audit event=%s actor=%s target=%s:%s case=%s", event_type, event.actor_id, target_type, target_id, case_id)
    return event
