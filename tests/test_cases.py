"""Severity framework, lifecycle transitions, outcomes, referrals."""

import pytest

from app.models import AuditEvent, Case
from app.services import cases as svc
from app.services.cases import CaseError
from tests.conftest import login, make_case, user_by_role


def test_severity_requires_reasoning_and_records_history(app):
    case, _ = make_case()
    sup = user_by_role("supervisor")
    with pytest.raises(CaseError):
        svc.assess_severity(case, sup, 3, "too short")
    with pytest.raises(CaseError):
        svc.assess_severity(case, sup, 5, "Level five does not exist in this framework at all.")
    svc.assess_severity(case, sup, 2, "Coercion reported but no immediate danger indicated by the reporter.")
    assert case.severity_level == 2 and case.status == "triage"
    svc.assess_severity(case, sup, 3, "New messages show daily threats; escalating to high concern.")
    svc.assess_severity(case, user_by_role("legal"), 2, "After review with the reporter the threats have stopped.", is_override=True)
    directions = [a.direction for a in case.severity_assessments]
    assert directions == ["initial", "escalation", "de_escalation"]
    assert case.severity_assessments[-1].is_override
    assert AuditEvent.query.filter_by(event_type="case.severity", case_id=case.id).count() == 3


def test_new_case_has_no_severity_until_human_assesses(app):
    case, _ = make_case(immediate_danger="yes")
    assert case.severity_level is None and case.safety_flag is True


def test_lifecycle_transitions_are_enforced(app):
    case, _ = make_case()
    sup = user_by_role("supervisor")
    with pytest.raises(CaseError):
        svc.change_status(case, sup, "resolved", "Trying to skip straight to resolved.")
    svc.assess_severity(case, sup, 1, "Routine information request, nothing urgent reported here.")
    svc.assign(case, sup, user_by_role("support"))
    assert case.status == "assigned"
    svc.change_status(case, sup, "under_review", "Support worker has started reviewing.")
    svc.change_status(case, sup, "referral_action", "Referral to counselling offered and accepted.")
    svc.change_status(case, sup, "follow_up", "Checking the referral outcome with the reporter.")
    svc.change_status(case, sup, "resolved", "Reporter confirmed the referral helped.")
    assert case.closed_at is not None and case.retention_review_at is not None
    svc.change_status(case, sup, "closed", "Closing after resolution.")
    svc.change_status(case, sup, "appealed", "Reporter asked for a second look.")
    svc.change_status(case, sup, "reopened", "Appeal upheld; reopening.")
    assert case.closed_at is None
    statuses = [s.to_status for s in case.status_changes]
    assert statuses[0] == "submitted" and statuses[-1] == "reopened"
    with pytest.raises(CaseError):
        svc.change_status(case, sup, "closed", "Not allowed directly from reopened.")


def test_status_change_needs_reason_via_http(client):
    login(client, "supervisor")
    case = Case.query.filter_by(category="harassment").one()
    r = client.post(f"/workspace/cases/{case.reference}/status", data={"to_status": "resolved", "reason": "ok"})
    assert r.status_code == 302 and case.status == "under_review"
    r = client.post(
        f"/workspace/cases/{case.reference}/status", data={"to_status": "resolved", "reason": "Reporter confirmed the college has acted."}
    )
    assert case.status == "resolved"


def test_reopen_requires_permission(client):
    case = Case.query.filter_by(category="harassment").one()
    sup = user_by_role("supervisor")
    svc.change_status(case, sup, "resolved", "Resolved for the purpose of this test.")
    login(client, "support")  # support lacks case.reopen
    r = client.post(
        f"/workspace/cases/{case.reference}/status", data={"to_status": "reopened", "reason": "Trying to reopen without the permission."}
    )
    assert r.status_code == 403


def test_outcomes_require_confirmation_and_second_person_verification(app):
    case = Case.query.filter_by(category="abuse_violence").one()
    legal = user_by_role("legal")
    with pytest.raises(CaseError):
        svc.record_outcome(
            case,
            legal,
            {"outcome_type": "complaint_submitted", "finding_status": "allegation", "description": "Complaint lodged with the office."},
        )
    outcome = svc.record_outcome(
        case,
        legal,
        {
            "outcome_type": "complaint_submitted",
            "finding_status": "under_official_investigation",
            "description": "Complaint lodged with the office.",
            "confirmation_reference": "ACK-2026-17",
        },
    )
    assert outcome.verified is False
    with pytest.raises(CaseError):
        svc.verify_outcome(outcome, legal)
    svc.verify_outcome(outcome, user_by_role("supervisor"))
    assert outcome.verified and outcome.verified_by_id == user_by_role("supervisor").id
    with pytest.raises(CaseError):
        svc.record_outcome(
            case,
            legal,
            {
                "outcome_type": "official_outcome_verified",
                "finding_status": "guilty",
                "description": "Invalid finding vocabulary should fail.",
            },
        )


def test_referral_confirmation_requires_reference(app):
    case = Case.query.filter_by(category="abuse_violence").one()
    referral = case.referrals[0]
    with pytest.raises(CaseError):
        svc.update_referral(referral, user_by_role("legal"), "confirmed", "", None)
    svc.update_referral(referral, user_by_role("legal"), "confirmed", "LA-4411", "Confirmed by the office.")
    assert referral.status == "confirmed"


def test_reporter_update_refuses_identifiers(client):
    login(client, "support")
    case = Case.query.filter_by(category="harassment").one()
    r = client.post(f"/workspace/cases/{case.reference}/update", data={"body": "Call us at 01712345678 tomorrow."})
    assert r.status_code == 302
    assert not any(u.kind == "message" and "01712345678" in u.body for u in case.updates)
    client.post(f"/workspace/cases/{case.reference}/update", data={"body": "We have written to the college and will update you here."})
    assert any("written to the college" in u.body for u in case.updates)


def test_assign_moves_submitted_case_into_assigned(app):
    case, _ = make_case()
    svc.assign(case, user_by_role("supervisor"), user_by_role("support"))
    assert case.status == "assigned" and case.is_assigned_to(user_by_role("support").id)
    with pytest.raises(CaseError):
        svc.assign(case, user_by_role("supervisor"), user_by_role("reporter"))
