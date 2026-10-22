import io

from app import db
from app.models import AuditEvent, Case, Evidence, ReporterIdentity
from tests.conftest import BASE_REPORT, login, make_case


def test_anonymous_report_stores_no_identity(client):
    r = client.post("/report/new", data={**BASE_REPORT, "identity_name": "Should Be Ignored", "identity_phone": "01711111111"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/report/submitted")
    case = Case.query.order_by(Case.id.desc()).first()
    assert case.submission_type == "anonymous" and case.has_identity is False
    assert ReporterIdentity.query.filter_by(case_id=case.id).first() is None
    assert case.department == "support" and case.status == "submitted" and case.severity_level is None
    assert case.reference.startswith("HL-") and len(case.tracking_secret_hash) == 64


def test_receipt_page_shows_reference_and_key_once(client):
    client.post("/report/new", data=BASE_REPORT)
    r = client.get("/report/submitted")
    case = Case.query.order_by(Case.id.desc()).first()
    assert case.reference.encode() in r.data
    assert b'id="secret"' in r.data
    r = client.post("/report/submitted/dismiss")
    assert r.status_code == 302
    assert client.get("/report/submitted").status_code == 302


def test_confidential_report_encrypts_identity_separately(client):
    data = {
        **BASE_REPORT,
        "submission_type": "confidential",
        "identity_name": "Rina Example",
        "identity_phone": "01799999999",
        "identity_email": "rina@example.org",
        "do_not_contact": "my brother",
        "contact_preference": "phone",
        "consent_contact": "y",
    }
    client.post("/report/new", data=data)
    case = Case.query.order_by(Case.id.desc()).first()
    assert case.has_identity is True and case.consent_contact is True and case.contact_preference == "phone"
    identity = ReporterIdentity.query.filter_by(case_id=case.id).one()
    raw = identity.payload_enc
    assert b"Rina" not in raw and b"01799999999" not in raw  # encrypted at rest
    assert identity.read_payload()["phone"] == "01799999999"
    # the narrative row itself carries no identity columns
    assert "Rina" not in case.narrative and "01799999999" not in (case.title + case.narrative)


def test_consent_is_required(client):
    data = {k: v for k, v in BASE_REPORT.items() if k != "consent_process"}
    r = client.post("/report/new", data=data)
    assert r.status_code == 200 and Case.query.count() == 6  # only the seeded cases


def test_honeypot_blocks_bots(client):
    r = client.post("/report/new", data={**BASE_REPORT, "website": "http://spam.example"})
    assert r.status_code == 200 and Case.query.count() == 6


def test_immediate_danger_sets_safety_flag_and_child_flag(client):
    client.post("/report/new", data={**BASE_REPORT, "immediate_danger": "yes", "child_involved": "y"})
    case = Case.query.order_by(Case.id.desc()).first()
    assert case.safety_flag and case.child_safety_flag


def test_tracking_requires_reference_and_secret(client):
    case, secret = make_case()
    r = client.post("/track/", data={"reference": case.reference, "secret": "WRONGSECRET123"})
    assert r.status_code == 200 and b"No case matches" in r.data
    assert client.get(f"/track/{case.reference}").status_code == 403
    r = client.post("/track/", data={"reference": case.reference.lower().replace("-", ""), "secret": secret.lower()})
    assert r.status_code == 302
    r = client.get(f"/track/{case.reference}")
    assert r.status_code == 200 and b"Waiting for human review" in r.data
    assert AuditEvent.query.filter_by(event_type="track.opened").count() == 1


def test_reporter_can_message_team_and_forget_device(client):
    case, secret = make_case()
    client.post("/track/", data={"reference": case.reference, "secret": secret})
    r = client.post(f"/track/{case.reference}/message", data={"body": "Is there any update? I am worried."})
    assert r.status_code == 302
    assert any(u.kind == "reporter_message" for u in case.updates)
    client.post(f"/track/{case.reference}/forget")
    assert client.get(f"/track/{case.reference}").status_code == 403


def test_tracking_page_never_shows_identity_or_staff_notes(client):
    case, secret = make_case(submission_type="confidential", identity_name="Hidden Name", identity_phone="01755555555")
    login_client = client
    login(login_client, "supervisor")
    from app.services import cases as svc
    from tests.conftest import user_by_role

    svc.assess_severity(case, user_by_role("supervisor"), 3, "Daily threats and coercion; credible risk of image-based abuse.")
    svc.add_note(case, user_by_role("supervisor"), "Internal note: reporter lives near the market.")
    client.post("/auth/logout")
    client.post("/track/", data={"reference": case.reference, "secret": secret})
    r = client.get(f"/track/{case.reference}")
    assert r.status_code == 200
    assert b"Hidden Name" not in r.data and b"01755555555" not in r.data and b"Internal note" not in r.data
    assert b"Level" not in r.data  # severity is not surfaced as a label to the reporter


def test_evidence_upload_with_report(client, app):
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    data = {**BASE_REPORT, "evidence": [(io.BytesIO(png), "proof.png")], "evidence_description": "screenshot"}
    r = client.post("/report/new", data=data, content_type="multipart/form-data")
    assert r.status_code == 302
    ev = Evidence.query.order_by(Evidence.id.desc()).first()
    assert ev.mime_type == "image/png" and ev.scan_status == "not_scanned" and ev.uploaded_by_reporter
    assert ev.sha256 and ev.size_bytes == len(png)
    from app.services.uploads import evidence_path

    path = evidence_path(ev)
    assert path.exists() and str(app.static_folder) not in str(path)
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_logged_in_reporter_links_confidential_case_only(client):
    login(client, "reporter")
    client.post("/report/new", data=BASE_REPORT)  # anonymous: no link to the account
    assert Case.query.order_by(Case.id.desc()).first().reporter_user_id is None
    client.post("/report/new", data={**BASE_REPORT, "submission_type": "confidential", "identity_name": "Me"})
    case = Case.query.order_by(Case.id.desc()).first()
    assert case.reporter_user_id is not None
    r = client.get("/my-reports")
    assert case.reference.encode() in r.data
    db.session.rollback()
