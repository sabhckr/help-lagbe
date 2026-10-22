"""Case-level authorisation (need-to-know). Every protected view calls these; templates only
hide what the server already refuses."""

from __future__ import annotations

from flask import abort
from sqlalchemy import ColumnElement, or_

from app import permissions as P
from app.models.case import STATUS_SUBMITTED, STATUS_TRIAGE, Case, CaseAssignment


def can_view_metadata(user, case: Case) -> bool:
    """Reference, category, status, severity, department — no narrative."""
    if not user.is_authenticated or not user.is_staff:
        return False
    if user.can(P.CASE_VIEW_METADATA_ANY):
        return True
    if case.is_assigned_to(user.id):
        return True
    if user.can(P.CASE_TRIAGE_ALL) and case.status in (STATUS_SUBMITTED, STATUS_TRIAGE):
        return True
    if user.can(P.CASE_VIEW_QUEUE) and case.department == user.department:
        return True
    if user.can(P.MOD_QUEUE) and (case.moderation_hold or case.is_spam):
        return True
    return False


def can_view_narrative(user, case: Case) -> bool:
    """Narrative, notes, evidence list. Assigned staff; own-department triage; safeguarding lead."""
    if not user.is_authenticated or not user.is_staff or not user.can(P.CASE_VIEW_NARRATIVE):
        return False
    if case.is_assigned_to(user.id):
        return True
    in_intake = case.status in (STATUS_SUBMITTED, STATUS_TRIAGE)
    if in_intake and user.can(P.CASE_TRIAGE) and case.department == user.department:
        return True
    if in_intake and user.can(P.CASE_TRIAGE_ALL):
        return True
    if user.can(P.SUPPORT_SUPERVISE) and case.department == user.department:
        return True
    if user.can(P.MOD_QUEUE) and (case.moderation_hold or case.is_spam):
        return True
    return False


def can_act_on_case(user, case: Case) -> bool:
    """Record notes/status/severity: must be able to read the narrative."""
    return can_view_narrative(user, case)


def require_metadata(user, case: Case) -> None:
    if not can_view_metadata(user, case):
        abort(403)


def require_narrative(user, case: Case) -> None:
    if not can_view_narrative(user, case):
        abort(403)


def queue_query(user):
    """Cases this user may see in lists."""
    q = Case.query
    if user.can(P.CASE_VIEW_METADATA_ANY):
        return q
    conditions: list[ColumnElement[bool]] = [
        Case.id.in_(CaseAssignment.query.with_entities(CaseAssignment.case_id).filter_by(user_id=user.id, active=True))
    ]
    if user.can(P.CASE_VIEW_QUEUE) and user.department:
        conditions.append(Case.department == user.department)
    if user.can(P.CASE_TRIAGE_ALL):
        conditions.append(Case.status.in_((STATUS_SUBMITTED, STATUS_TRIAGE)))
    if user.can(P.MOD_QUEUE):
        conditions.append(or_(Case.moderation_hold.is_(True), Case.is_spam.is_(True)))
    return q.filter(or_(*conditions))


def can_see_note(user, note) -> bool:
    if note.visibility == "legal_privileged":
        return user.can(P.LEGAL_PRIVILEGED_NOTES)
    if note.visibility == "safeguarding":
        return user.can_any(P.SUPPORT_CHAT, P.SUPPORT_SUPERVISE, P.CASE_TRIAGE_ALL) or user.role == P.ROLE_SUPPORT
    return True
