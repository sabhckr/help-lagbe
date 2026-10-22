from app import db
from app.models import AuditEvent, Case, DepartmentConfig, EmergencyContact, User
from tests.conftest import login, user_by_role


def test_admin_creates_staff_with_policy_and_temp_password(client):
    login(client, "admin")
    r = client.post(
        "/workspace/admin/users", data={"name": "New Agent", "email": "agent9@helplagbe.local", "role": "support", "password": "weak"}
    )
    assert r.status_code == 200 and User.query.filter_by(email="agent9@helplagbe.local").first() is None
    r = client.post(
        "/workspace/admin/users",
        data={"name": "New Agent", "email": "agent9@helplagbe.local", "role": "support", "password": "a-strong-temp-password-7"},
    )
    assert r.status_code == 302
    user = User.query.filter_by(email="agent9@helplagbe.local").one()
    assert user.must_change_password and not user.mfa_enabled and user.created_by_id == user_by_role("admin").id


def test_admin_cannot_demote_self_and_role_change_is_logged(client):
    admin = login(client, "admin")
    client.post(f"/workspace/admin/users/{admin.id}/role", data={"role": "support", "active": "y", "reason": "Trying to demote myself."})
    assert User.query.get(admin.id).role == "admin"
    target = user_by_role("action")
    client.post(
        f"/workspace/admin/users/{target.id}/role", data={"role": "moderator", "active": "y", "reason": "Moving to the moderation team."}
    )
    assert User.query.get(target.id).role == "moderator"
    ev = AuditEvent.query.filter_by(event_type="admin.role_changed").one()
    assert ev.target_id == target.id and "moderation team" in ev.reason


def test_department_cannot_be_marked_staffed_without_staff(client):
    login(client, "admin")
    for u in User.query.filter_by(role="moderator").all():
        u.active = False
    db.session.commit()
    r = client.post("/workspace/admin/departments/moderation", data={"moderation-is_staffed": "y", "moderation-accepts_cases": "y"})
    assert r.status_code == 302
    assert DepartmentConfig.query.filter_by(department="moderation").one().is_staffed is False
    r = client.post(
        "/workspace/admin/departments/support",
        data={"support-is_staffed": "y", "support-accepts_cases": "y", "support-hours_en": "Daily 10-18"},
    )
    assert DepartmentConfig.query.filter_by(department="support").one().hours_en == "Daily 10-18"


def test_unverified_contacts_hidden_from_public_until_verified(client):
    r = client.get("/get-help")
    assert b"999" not in r.data.split(b"contacts-title")[1][:2000] if b"contacts-title" in r.data else True
    assert b"No verified emergency numbers" in r.data
    login(client, "admin")
    contact = EmergencyContact.query.filter_by(number="999").one()
    client.post(f"/workspace/admin/contacts/{contact.id}/verify", data={"verification_note": "Called on 22 Oct, operator answered"})
    assert EmergencyContact.query.get(contact.id).verified
    client.post("/auth/logout")
    r = client.get("/get-help")
    assert b'href="tel:999"' in r.data


def test_audit_export_requires_reason_and_logs_itself(client):
    login(client, "admin")
    r = client.post("/workspace/admin/audit/export", data={"reason": "short"})
    assert r.status_code == 302
    r = client.post("/workspace/admin/audit/export", data={"reason": "Quarterly governance review of sensitive access."})
    assert r.status_code == 200 and r.mimetype == "text/csv" and b"event_type" in r.data
    assert AuditEvent.query.filter_by(event_type="audit.export").count() == 1
    assert b"Fictional Reporter" not in r.data  # no identities in exports


def test_retention_purge_only_for_closed_cases_and_logged(client):
    login(client, "admin")
    case = Case.query.filter_by(category="domestic_violence").one()
    r = client.post(
        f"/workspace/admin/retention/{case.reference}/purge-identity",
        data={"reason": "Retention period elapsed; identity no longer needed."},
    )
    assert r.status_code == 302 and case.identity.purged_at is None  # still open
    from app.services import cases as svc

    sup = user_by_role("supervisor")
    svc.change_status(case, sup, "resolved", "Resolved for retention test purposes.")
    client.post(
        f"/workspace/admin/retention/{case.reference}/purge-identity",
        data={"reason": "Retention period elapsed; identity no longer needed."},
    )
    assert case.identity.purged_at is not None and case.identity.payload_enc == b""
    assert AuditEvent.query.filter_by(event_type="identity.purge").count() == 1


def test_health_page_reports_truthfully(client):
    login(client, "admin")
    r = client.get("/workspace/admin/health")
    assert r.status_code == 200 and b"not configured" in r.data  # scanner + email honestly missing
