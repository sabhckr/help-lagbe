"""Role isolation, need-to-know, identity unlock and audit."""

from app.models import AuditEvent, Case
from app.services import cases as svc
from app.services import identity as identity_svc
from tests.conftest import login, make_case, user_by_role


def _dv_case() -> Case:
    return Case.query.filter_by(category="domestic_violence").one()


def test_reporter_cannot_reach_workspace(client):
    login(client, "reporter")
    for url in (
        "/workspace/",
        "/workspace/cases",
        "/workspace/admin/users",
        "/workspace/admin/audit",
        "/workspace/support",
        "/workspace/publications",
    ):
        assert client.get(url).status_code == 403, url


def test_anonymous_is_redirected_to_login(client):
    r = client.get("/workspace/cases")
    assert r.status_code == 302 and "/auth/login" in r.headers["Location"]


def test_support_agent_cannot_open_other_departments_case(client):
    login(client, "support")
    cyber_case = Case.query.filter_by(category="account_takeover").one()  # routed to cyber, assigned to cyber only
    assert client.get(f"/workspace/cases/{cyber_case.reference}").status_code == 403
    # but can open a case in their own department
    own = Case.query.filter_by(category="eve_teasing").one()
    r = client.get(f"/workspace/cases/{own.reference}")
    assert r.status_code == 200 and own.title.encode() in r.data


def test_queue_only_lists_visible_cases(client):
    login(client, "cyber")
    r = client.get("/workspace/cases?scope=all")
    assert Case.query.filter_by(category="account_takeover").one().reference.encode() in r.data
    assert Case.query.filter_by(category="eve_teasing").one().reference.encode() not in r.data


def test_admin_sees_metadata_but_not_narrative(client):
    login(client, "admin")
    case = _dv_case()
    r = client.get(f"/workspace/cases/{case.reference}")
    assert r.status_code == 200
    assert b"Narrative restricted" in r.data
    assert case.narrative[:40].encode() not in r.data
    assert b"break-glass" in r.data.lower()


def test_admin_break_glass_requires_reason_and_is_logged(client):
    login(client, "admin")
    case = _dv_case()
    r = client.post(f"/workspace/cases/{case.reference}/break-glass", data={"reason": "short"})
    assert r.status_code == 302 and AuditEvent.query.filter_by(event_type="case.break_glass").count() == 0
    r = client.post(
        f"/workspace/cases/{case.reference}/break-glass", data={"reason": "Reviewing a complaint about how this case was handled."}
    )
    assert r.status_code == 200 and case.narrative[:40].encode() in r.data
    assert b"legal_privileged" not in r.data
    ev = AuditEvent.query.filter_by(event_type="case.break_glass").one()
    assert ev.actor_id == user_by_role("admin").id and ev.case_id == case.id and "complaint" in ev.reason


def test_admin_cannot_record_actions_on_cases(client):
    login(client, "admin")
    case = _dv_case()
    r = client.post(
        f"/workspace/cases/{case.reference}/severity", data={"level": "1", "reasoning": "Admin trying to downgrade the severity level."}
    )
    assert r.status_code == 403
    r = client.post(f"/workspace/cases/{case.reference}/note", data={"body": "admin note", "visibility": "case_team"})
    assert r.status_code == 403


def test_identity_unlock_requires_assignment_reason_and_logs(client):
    case = _dv_case()  # assigned to support + legal
    login(client, "cyber")  # cyber holds the permission but is not assigned
    r = client.post(f"/workspace/cases/{case.reference}/identity", data={"reason": "I would like to see who reported this case."})
    assert r.status_code == 403
    assert AuditEvent.query.filter_by(event_type="identity.unlock_refused").count() >= 1
    client.post("/auth/logout")
    login(client, "legal")
    r = client.post(f"/workspace/cases/{case.reference}/identity", data={"reason": "tiny"})
    assert r.status_code == 302  # reason too short: refused before any decrypt
    r = client.post(
        f"/workspace/cases/{case.reference}/identity", data={"reason": "Arrange the legal aid appointment the reporter agreed to."}
    )
    assert r.status_code == 200 and b"Fictional Reporter D" in r.data and b"This access has been logged" in r.data
    ev = AuditEvent.query.filter_by(event_type="identity.unlock", case_id=case.id).order_by(AuditEvent.id.desc()).first()
    assert ev.actor_role == "legal" and "legal aid" in ev.reason
    assert case.identity.access_count == 1
    # the identity never appears on the ordinary case page
    r = client.get(f"/workspace/cases/{case.reference}")
    assert b"Fictional Reporter D" not in r.data and b"reporter-d@example.invalid" not in r.data


def test_editorial_cannot_unlock_identity(client):
    case = Case.query.filter_by(category="bribery").one()  # editorial case
    from app.models import ReporterIdentity

    identity = ReporterIdentity(case_id=case.id)
    identity.set_payload({"name": "Secret Source"})
    from app import db

    db.session.add(identity)
    case.has_identity = True
    db.session.commit()
    login(client, "editorial")
    r = client.post(f"/workspace/cases/{case.reference}/identity", data={"reason": "Need to verify the source for the story."})
    assert r.status_code == 403
    assert client.get(f"/workspace/cases/{case.reference}").status_code == 200


def test_legal_privileged_notes_hidden_from_non_legal(client):
    case = _dv_case()
    login(client, "support")
    r = client.get(f"/workspace/cases/{case.reference}")
    assert r.status_code == 200 and b"Protection order pathway" not in r.data
    client.post("/auth/logout")
    login(client, "legal")
    r = client.get(f"/workspace/cases/{case.reference}")
    assert b"Protection order pathway" in r.data


def test_moderator_cannot_read_ordinary_cases_but_sees_held_ones(client):
    case = _dv_case()
    login(client, "moderator")
    assert client.get(f"/workspace/cases/{case.reference}").status_code == 403
    case.moderation_hold = True
    from app import db

    db.session.commit()
    assert client.get(f"/workspace/cases/{case.reference}").status_code == 200


def test_permission_matrix_page_and_admin_only_areas(client):
    login(client, "support")
    assert client.get("/workspace/admin/permissions").status_code == 200
    for url in ("/workspace/admin/users", "/workspace/admin/settings", "/workspace/admin/health", "/workspace/admin/retention"):
        assert client.get(url).status_code == 403, url
    assert client.get("/workspace/admin/audit").status_code == 200  # department view only
    r = client.get("/workspace/admin/audit?sensitive=1")
    assert b"identity.unlock" not in r.data or b"legal" not in r.data


def test_service_layer_refuses_unassigned_unlock(app):
    case, _ = make_case(submission_type="confidential", identity_name="X")
    support = user_by_role("support")
    svc.assign(case, user_by_role("supervisor"), support)
    assert identity_svc.unlock(case, support, "Need to call the reporter back as agreed.")["name"] == "X"
    try:
        identity_svc.unlock(case, user_by_role("action"), "Need to call the reporter back as agreed.")
        raise AssertionError("unassigned action officer unlocked identity")
    except identity_svc.IdentityAccessDenied:
        pass
