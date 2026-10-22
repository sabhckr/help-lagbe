"""Case lifecycle: creation, triage, severity, status, assignment, notes, updates, referrals, outcomes.
All functions enforce the vocabulary and write audit/history rows; routes only do permission checks."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from flask import current_app

from app import permissions as P
from app.crypto import hash_secret
from app.extensions import db
from app.models.base import random_reference, random_secret, utcnow
from app.models.case import (
    CONTACT_PREFERENCES,
    CONTACT_TRACKING,
    DANGER_YES,
    FINDING_STATUSES,
    OUTCOME_TYPES,
    REFERRAL_STATUSES,
    REFERRAL_TYPES,
    STATUS_CLOSED,
    STATUS_RESOLVED,
    STATUS_SUBMITTED,
    STATUS_TRIAGE,
    SUBMISSION_ANONYMOUS,
    SUBMISSION_CONFIDENTIAL,
    Case,
    CaseAssignment,
    CaseNote,
    CaseOutcome,
    CaseUpdate,
    Referral,
    SeverityAssessment,
    StatusChange,
)
from app.models.identity import ReporterIdentity
from app.services import audit


class CaseError(ValueError):
    """Raised with a translation key when a transition or input is not allowed."""


def _unique_reference() -> str:
    for _ in range(20):
        ref = random_reference()
        if not Case.query.filter_by(reference=ref).first():
            return ref
    raise RuntimeError("could not allocate a unique case reference")


def create_case(data: dict[str, Any], *, reporter_user=None, language: str = "en") -> tuple[Case, str]:
    """Create a case from validated form data. Returns (case, tracking_secret).
    The tracking secret is shown to the reporter exactly once and stored only as a hash."""
    submission_type = SUBMISSION_CONFIDENTIAL if data.get("submission_type") == SUBMISSION_CONFIDENTIAL else SUBMISSION_ANONYMOUS
    if not data.get("consent_process"):
        raise CaseError("report.error_consent_required")
    category = data["category"]
    if category not in P.CATEGORIES:
        raise CaseError("report.error_category")
    contact_pref = data.get("contact_preference") or CONTACT_TRACKING
    if contact_pref not in CONTACT_PREFERENCES:
        contact_pref = CONTACT_TRACKING
    if submission_type == SUBMISSION_ANONYMOUS and contact_pref in ("phone", "email"):
        # Anonymous means we hold no contact details; fall back to the tracking page.
        contact_pref = CONTACT_TRACKING

    secret = random_secret()
    immediate_danger = data.get("immediate_danger") or "unsure"
    child_involved = bool(data.get("child_involved"))
    case = Case(
        reference=_unique_reference(),
        tracking_secret_hash=hash_secret(secret),
        title=data["title"].strip(),
        narrative=data["narrative"].strip(),
        category=category,
        approximate_time=(data.get("approximate_time") or "").strip() or None,
        location_text=(data.get("location_text") or "").strip() or None,
        submission_type=submission_type,
        has_identity=False,
        reporter_user_id=getattr(reporter_user, "id", None) if submission_type == SUBMISSION_CONFIDENTIAL else None,
        immediate_danger=immediate_danger,
        child_involved=child_involved,
        safety_flag=(immediate_danger == DANGER_YES),
        child_safety_flag=child_involved or category == "child_abuse",
        consent_process=True,
        consent_publication=bool(data.get("consent_publication")),
        consent_contact=bool(data.get("consent_contact")) and submission_type == SUBMISSION_CONFIDENTIAL,
        contact_preference=contact_pref,
        language=language,
        department=P.default_department_for_category(category),
        status=STATUS_SUBMITTED,
    )
    db.session.add(case)
    db.session.flush()

    if submission_type == SUBMISSION_CONFIDENTIAL:
        identity_payload = {
            "name": (data.get("identity_name") or "").strip(),
            "phone": (data.get("identity_phone") or "").strip(),
            "email": (data.get("identity_email") or "").strip(),
            "safe_contact_notes": (data.get("safe_contact_notes") or "").strip(),
            "do_not_contact": (data.get("do_not_contact") or "").strip(),
            "safe_hours": (data.get("safe_hours") or "").strip(),
        }
        if any(identity_payload.values()) or reporter_user is not None:
            if reporter_user is not None and not identity_payload["email"]:
                identity_payload["email"] = reporter_user.email
            identity = ReporterIdentity(case_id=case.id)
            identity.set_payload(identity_payload)
            db.session.add(identity)
            case.has_identity = True

    db.session.add(StatusChange(case_id=case.id, actor_id=None, from_status="", to_status=STATUS_SUBMITTED, reason="Submitted by reporter"))
    db.session.add(CaseUpdate(case_id=case.id, kind="status", body="track.update_received"))
    audit.record(
        "case.created",
        target_type="case",
        target_id=case.id,
        case_id=case.id,
        details={"category": category, "type": submission_type, "safety_flag": case.safety_flag},
    )
    db.session.commit()
    return case, secret


# ---- Triage / severity ---------------------------------------------------------------------
def assess_severity(case: Case, user, level: int, reasoning: str, *, is_override: bool = False) -> SeverityAssessment:
    if level not in (1, 2, 3, 4):
        raise CaseError("severity.error_level")
    reasoning = (reasoning or "").strip()
    if len(reasoning) < 20:
        raise CaseError("severity.error_reasoning")
    previous = case.severity_level
    if previous is None:
        direction = "initial"
    elif level > previous:
        direction = "escalation"
    elif level < previous:
        direction = "de_escalation"
    else:
        direction = "reaffirmed"
    assessment = SeverityAssessment(
        case_id=case.id,
        assessor_id=user.id,
        previous_level=previous,
        level=level,
        direction=direction,
        is_override=is_override,
        reasoning=reasoning,
    )
    case.severity_level = level
    if case.status == STATUS_SUBMITTED:
        _transition(case, user, STATUS_TRIAGE, "Severity assessed by human reviewer")
    db.session.add(assessment)
    audit.record(
        "case.severity",
        actor=user,
        target_type="case",
        target_id=case.id,
        case_id=case.id,
        details={"from": previous, "to": level, "direction": direction, "override": is_override},
    )
    db.session.commit()
    return assessment


def route_case(case: Case, user, department: str, reason: str) -> None:
    if department not in P.DEPARTMENTS:
        raise CaseError("case.error_department")
    old = case.department
    case.department = department
    db.session.add(
        CaseNote(
            case_id=case.id, author_id=user.id, note_type="routing", body=f"Routed from {old or '-'} to {department}: {reason.strip()}"
        )
    )
    audit.record("case.routed", actor=user, target_type="case", target_id=case.id, case_id=case.id, details={"from": old, "to": department})
    db.session.commit()


def _transition(case: Case, user, to_status: str, reason: str) -> StatusChange:
    if not case.can_transition_to(to_status):
        raise CaseError("case.error_transition")
    change = StatusChange(case_id=case.id, actor_id=getattr(user, "id", None), from_status=case.status, to_status=to_status, reason=reason)
    case.status = to_status
    if to_status in (STATUS_RESOLVED, STATUS_CLOSED):
        case.closed_at = utcnow()
        days = current_app.config.get("DATA_RETENTION_DAYS_CLOSED_CASES", 365)
        case.retention_review_at = date.today() + timedelta(days=days)
    else:
        case.closed_at = None
    db.session.add(change)
    db.session.add(CaseUpdate(case_id=case.id, author_id=getattr(user, "id", None), kind="status", body=f"status.{to_status}"))
    return change


def change_status(case: Case, user, to_status: str, reason: str) -> StatusChange:
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise CaseError("case.error_reason")
    change = _transition(case, user, to_status, reason)
    audit.record(
        "case.status",
        actor=user,
        target_type="case",
        target_id=case.id,
        case_id=case.id,
        details={"from": change.from_status, "to": to_status},
    )
    db.session.commit()
    return change


def assign(case: Case, user, assignee, role_in_case: str = "lead") -> CaseAssignment:
    if not assignee.is_staff or not assignee.active:
        raise CaseError("case.error_assignee")
    existing = CaseAssignment.query.filter_by(case_id=case.id, user_id=assignee.id, active=True).first()
    if existing:
        return existing
    assignment = CaseAssignment(case_id=case.id, user_id=assignee.id, assigned_by_id=user.id, role_in_case=role_in_case)
    db.session.add(assignment)
    if case.status in (STATUS_SUBMITTED, STATUS_TRIAGE):
        if case.status == STATUS_SUBMITTED:
            _transition(case, user, STATUS_TRIAGE, "Assignment started")
        _transition(case, user, "assigned", f"Assigned to {assignee.role}")
    audit.record(
        "case.assigned",
        actor=user,
        target_type="case",
        target_id=case.id,
        case_id=case.id,
        details={"assignee": assignee.id, "role_in_case": role_in_case},
    )
    db.session.commit()
    return assignment


def unassign(case: Case, user, assignee_id: int) -> None:
    for a in case.assignments:
        if a.user_id == assignee_id and a.active:
            a.active = False
            a.ended_at = utcnow()
    audit.record("case.unassigned", actor=user, target_type="case", target_id=case.id, case_id=case.id, details={"assignee": assignee_id})
    db.session.commit()


def add_note(case: Case, user, body: str, *, note_type: str = "note", visibility: str = "case_team") -> CaseNote:
    body = (body or "").strip()
    if not body:
        raise CaseError("validation.required")
    if visibility == "legal_privileged" and not user.can(P.LEGAL_PRIVILEGED_NOTES):
        visibility = "case_team"
    note = CaseNote(case_id=case.id, author_id=user.id, note_type=note_type, visibility=visibility, body=body)
    db.session.add(note)
    db.session.commit()
    return note


def add_reporter_update(case: Case, user, body: str) -> CaseUpdate:
    body = (body or "").strip()
    if not body:
        raise CaseError("validation.required")
    update = CaseUpdate(case_id=case.id, author_id=user.id, kind="message", body=body)
    db.session.add(update)
    audit.record("case.reporter_update", actor=user, target_type="case", target_id=case.id, case_id=case.id)
    db.session.commit()
    return update


def add_reporter_message(case: Case, body: str) -> CaseUpdate:
    """A message from the reporter via the tracking page (never from staff)."""
    body = (body or "").strip()
    if not body:
        raise CaseError("validation.required")
    update = CaseUpdate(case_id=case.id, author_id=None, kind="reporter_message", body=body)
    db.session.add(update)
    db.session.commit()
    return update


def add_referral(case: Case, user, data: dict[str, Any]) -> Referral:
    if data.get("referral_type") not in REFERRAL_TYPES:
        raise CaseError("referral.error_type")
    org = (data.get("organisation") or "").strip()
    if not org:
        raise CaseError("validation.required")
    referral = Referral(
        case_id=case.id,
        owner_id=user.id,
        referral_type=data["referral_type"],
        organisation=org,
        consent_obtained=bool(data.get("consent_obtained")),
        status="offered",
        notes=(data.get("notes") or "").strip() or None,
        follow_up_due=data.get("follow_up_due"),
    )
    db.session.add(referral)
    audit.record(
        "case.referral",
        actor=user,
        target_type="case",
        target_id=case.id,
        case_id=case.id,
        details={"type": referral.referral_type, "consent": referral.consent_obtained},
    )
    db.session.commit()
    return referral


def update_referral(referral: Referral, user, status: str, confirmation_reference: str | None, notes: str | None) -> None:
    if status not in REFERRAL_STATUSES:
        raise CaseError("referral.error_status")
    if status == "confirmed" and not (confirmation_reference or "").strip():
        raise CaseError("referral.error_confirmation")
    referral.status = status
    if confirmation_reference:
        referral.confirmation_reference = confirmation_reference.strip()
    if notes:
        referral.notes = ((referral.notes or "") + "\n" + notes.strip()).strip()
    audit.record(
        "case.referral_update",
        actor=user,
        target_type="referral",
        target_id=referral.id,
        case_id=referral.case_id,
        details={"status": status},
    )
    db.session.commit()


def record_outcome(case: Case, user, data: dict[str, Any]) -> CaseOutcome:
    if data.get("outcome_type") not in OUTCOME_TYPES:
        raise CaseError("outcome.error_type")
    finding = data.get("finding_status") or "allegation"
    if finding not in FINDING_STATUSES:
        raise CaseError("outcome.error_finding")
    description = (data.get("description") or "").strip()
    if len(description) < 10:
        raise CaseError("outcome.error_description")
    confirmation = (data.get("confirmation_reference") or "").strip() or None
    needs_confirmation = data["outcome_type"] in ("complaint_submitted", "platform_action_confirmed", "official_outcome_verified")
    if needs_confirmation and not confirmation:
        raise CaseError("outcome.error_confirmation")
    outcome = CaseOutcome(
        case_id=case.id,
        recorded_by_id=user.id,
        outcome_type=data["outcome_type"],
        finding_status=finding,
        description=description,
        confirmation_reference=confirmation,
        verified=False,
    )
    db.session.add(outcome)
    audit.record(
        "case.outcome",
        actor=user,
        target_type="case",
        target_id=case.id,
        case_id=case.id,
        details={"type": outcome.outcome_type, "finding": finding},
    )
    db.session.commit()
    return outcome


def verify_outcome(outcome: CaseOutcome, user) -> None:
    if outcome.recorded_by_id == user.id:
        raise CaseError("outcome.error_self_verify")
    outcome.verified = True
    outcome.verified_by_id = user.id
    outcome.verified_at = utcnow()
    audit.record("case.outcome_verified", actor=user, target_type="outcome", target_id=outcome.id, case_id=outcome.case_id)
    db.session.commit()
