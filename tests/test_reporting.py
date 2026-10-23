"""The six-step reporting flow: drafts, validation, privacy, single submit and the receipt."""

import io

from app import db
from app.crypto import decrypt_bytes
from app.models import AuditEvent, Case, DraftFile, Evidence, ReportDraft, ReporterIdentity
from app.models.base import utcnow
from app.services import drafts
from app.services.uploads import evidence_root
from tests.conftest import ANSWERS, login, make_case, walk_report

SEEDED = 6


def _session_payload(app, client) -> str:
    cookie = client.get_cookie("hl_session")
    if cookie is None:
        return ""
    serializer = app.session_interface.get_signing_serializer(app)
    return str(serializer.loads(cookie.value))


def test_report_starts_at_step_one_and_old_url_redirects(client):
    r = client.get("/report/new")
    assert r.status_code == 302 and r.headers["Location"].endswith("/report/1")
    r = client.get("/report/1")
    assert r.status_code == 200 and b'name="category"' in r.data
    assert client.get("/report/9").status_code == 404


def test_full_anonymous_report_creates_one_case_and_shows_receipt(client, app):
    r = walk_report(client)
    assert r.status_code == 302 and r.headers["Location"].endswith("/report/received")
    assert Case.query.count() == SEEDED + 1
    case = Case.query.order_by(Case.id.desc()).first()
    assert case.category == "threats_blackmail" and case.department == "support"
    assert case.submission_type == "anonymous" and not case.has_identity
    assert case.status == "submitted" and case.severity_level is None
    assert ReporterIdentity.query.filter_by(case_id=case.id).first() is None
    page = client.get("/report/received")
    assert page.status_code == 200 and case.reference.encode() in page.data
    assert b"Your report has been received" in page.data


def test_one_time_key_never_sits_in_the_session_cookie(client, app):
    walk_report(client)
    page = client.get("/report/received").data.decode()
    secret = page.split('id="secret">')[1].split("<")[0]
    assert len(secret) == 14
    assert secret not in _session_payload(app, client)
    draft = ReportDraft.query.filter_by(status="submitted").one()
    assert draft.payload_enc is None and secret.encode() not in (draft.receipt_enc or b"")
    client.post("/report/received/dismiss")
    assert db.session.get(ReportDraft, draft.id).receipt_enc is None
    assert client.get("/report/received").status_code == 302


def test_double_submit_creates_only_one_case(client):
    walk_report(client)
    again = client.post("/report/6", data=ANSWERS[6])
    assert again.status_code == 302
    assert Case.query.count() == SEEDED + 1


def test_each_step_validates_and_explains(client):
    r = client.post("/report/1", data={})
    assert r.status_code == 422 and b"closest" in r.data
    client.post("/report/1", data={"category": "harassment"})
    client.post("/report/2", data={"immediate_danger": "no"})
    r = client.post("/report/3", data={"narrative": "short"})
    assert r.status_code == 422 and b"a few words" in r.data
    client.post("/report/3", data={"narrative": "A group of men shout at students at the college gate every day."})
    r = client.post("/report/4", data={"submission_type": "confidential", "contact_preference": "phone"})
    assert r.status_code == 422 and b"add a phone number" in r.data
    r = client.post("/report/4", data={"submission_type": "confidential", "identity_email": "not-an-email"})
    assert r.status_code == 422
    client.post("/report/4", data={"submission_type": "anonymous"})
    r = client.post("/report/6", data={})
    assert r.status_code == 422 and Case.query.count() == SEEDED


def test_review_sends_you_back_to_the_first_missing_answer(client):
    client.post("/report/1", data={"category": "online_harm"})
    r = client.get("/report/6")
    assert r.status_code == 302 and r.headers["Location"].endswith("/report/2")


def test_switching_language_keeps_saved_answers(client):
    client.post("/report/1", data={"category": "harassment"})
    client.post("/report/2", data={"immediate_danger": "no"})
    client.post("/report/3", data={"narrative": "Saved text that must survive a language switch."})
    r = client.get("/lang/bn?next=/report/3")
    assert r.status_code == 302 and r.headers["Location"].endswith("/report/3")
    page = client.get("/report/3").data.decode()
    assert '<html lang="bn"' in page and "Saved text that must survive a language switch." in page
    assert "কী ঘটেছে, বলুন" in page
    page = client.get("/report/1").data.decode()
    assert 'value="harassment" checked' in page


def test_danger_and_child_answers_set_flags_and_honest_message(client):
    walk_report(client, {2: {"immediate_danger": "yes", "child_involved": "y"}})
    case = Case.query.order_by(Case.id.desc()).first()
    assert case.safety_flag and case.child_safety_flag
    page = client.get("/report/received").data
    assert b"priority review" in page and b"No one has been alerted outside this system" in page


def test_child_safety_category_always_sets_the_child_flag(client):
    walk_report(client, {1: {"category": "child_safety"}})
    assert Case.query.order_by(Case.id.desc()).first().child_safety_flag


def test_confidential_report_keeps_identity_encrypted_and_separate(client):
    walk_report(
        client,
        {
            4: {
                "submission_type": "confidential",
                "identity_name": "Rina Example",
                "identity_phone": "01799999999",
                "identity_email": "rina@example.org",
                "contact_preference": "phone",
                "consent_contact": "y",
                "do_not_contact": "my brother",
            }
        },
    )
    case = Case.query.order_by(Case.id.desc()).first()
    assert case.has_identity and case.consent_contact and case.contact_preference == "phone"
    identity = ReporterIdentity.query.filter_by(case_id=case.id).one()
    assert b"Rina" not in identity.payload_enc and b"01799999999" not in identity.payload_enc
    assert identity.read_payload()["phone"] == "01799999999"
    assert "Rina" not in case.narrative and "Rina" not in case.title


def test_anonymous_choice_drops_any_identity_typed_earlier(client):
    client.post("/report/1", data={"category": "harassment"})
    client.post("/report/2", data={"immediate_danger": "no"})
    client.post("/report/3", data={"narrative": "Shouting at the bus stand most evenings this month."})
    client.post("/report/4", data={"submission_type": "confidential", "identity_name": "Should Not Stay"})
    client.post("/report/4", data={"submission_type": "anonymous", "identity_name": "Should Not Stay"})
    client.post("/report/5", data={"action": "continue"})
    client.post("/report/6", data=ANSWERS[6])
    case = Case.query.order_by(Case.id.desc()).first()
    assert case.submission_type == "anonymous" and not case.has_identity


def test_evidence_is_validated_encrypted_removable_and_moved_on_submit(client, app):
    for step in (1, 2, 3, 4):
        client.post(f"/report/{step}", data=ANSWERS[step])
    png = b"\x89PNG\r\n\x1a\n" + b"\x01" * 64
    r = client.post(
        "/report/5",
        data={"action": "continue", "evidence": [(io.BytesIO(png), "proof.png"), (io.BytesIO(b"MZfake"), "tool.exe")]},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"tool.exe" in r.data and b"not allowed" in r.data
    files = DraftFile.query.all()
    assert len(files) == 1 and files[0].original_name == "proof.png"
    assert files[0].data_enc != png and decrypt_bytes(files[0].data_enc) == png
    assert not (evidence_root() / "drafts").exists()
    client.post("/report/5", data={"evidence": [(io.BytesIO(png), "second.png")]}, content_type="multipart/form-data")
    second = DraftFile.query.filter_by(original_name="second.png").one()
    r = client.post(f"/report/5/remove/{second.id}")
    assert r.status_code == 302 and DraftFile.query.count() == 1
    client.post("/report/5", data={"action": "continue"})
    client.post("/report/6", data=ANSWERS[6])
    case = Case.query.order_by(Case.id.desc()).first()
    evidence = Evidence.query.filter_by(case_id=case.id).one()
    assert evidence.original_name == "proof.png" and evidence.uploaded_by_reporter
    assert DraftFile.query.count() == 0
    assert decrypt_bytes(evidence.data_enc) == png


def test_files_are_capped_per_report(client, app):
    app.config["EVIDENCE_MAX_FILES_PER_REPORT"] = 1
    for step in (1, 2, 3, 4):
        client.post(f"/report/{step}", data=ANSWERS[step])
    client.post(
        "/report/5",
        data={"evidence": [(io.BytesIO(b"hello one"), "a.txt"), (io.BytesIO(b"hello two"), "b.txt")]},
        content_type="multipart/form-data",
    )
    assert DraftFile.query.count() == 1


def test_expired_drafts_are_forgotten_and_purged(client, app):
    client.post("/report/1", data={"category": "other"})
    draft = ReportDraft.query.one()
    draft.expires_at = utcnow().replace(year=2000)
    db.session.commit()
    page = client.get("/report/1").data
    assert b'value="other" checked' not in page
    assert ReportDraft.query.count() == 0
    client.post("/report/1", data={"category": "other"})
    ReportDraft.query.one().expires_at = utcnow().replace(year=2000)
    db.session.commit()
    assert drafts.purge_expired() == 1


def test_honeypot_on_final_step_creates_nothing(client):
    walk_report(client, submit=False)
    r = client.post("/report/6", data={**ANSWERS[6], "website": "http://spam.example"})
    assert r.status_code == 422 and Case.query.count() == SEEDED
    assert AuditEvent.query.filter_by(event_type="report.honeypot").count() == 1


def test_draft_answers_are_encrypted_at_rest(client):
    client.post("/report/1", data={"category": "harassment"})
    client.post("/report/2", data={"immediate_danger": "no"})
    client.post("/report/3", data={"narrative": "PLAINTEXT-MARKER should never be stored readable."})
    draft = ReportDraft.query.one()
    assert b"PLAINTEXT-MARKER" not in draft.payload_enc


def test_signed_in_reporter_confidential_case_is_linked(client):
    login(client, "reporter")
    walk_report(client, {4: {"submission_type": "confidential", "identity_name": "Me"}})
    case = Case.query.order_by(Case.id.desc()).first()
    assert case.reporter_user_id is not None
    assert case.reference.encode() in client.get("/my-reports").data


def test_tracking_requires_reference_and_secret_and_shows_public_state(client):
    case, secret = make_case()
    r = client.post("/track/", data={"reference": case.reference, "secret": "WRONGSECRET123"})
    assert r.status_code == 200 and b"No case matches" in r.data
    assert client.get(f"/track/{case.reference}").status_code == 403
    r = client.post("/track/", data={"reference": case.reference.lower().replace("-", ""), "secret": secret.lower()})
    assert r.status_code == 302
    page = client.get(f"/track/{case.reference}")
    assert page.status_code == 200 and b"Received" in page.data and b"does not mean anything has been proven" in page.data
    assert AuditEvent.query.filter_by(event_type="track.opened").count() == 1


def test_tracking_page_hides_identity_notes_and_internal_words(client):
    case, secret = make_case(submission_type="confidential", identity_name="Hidden Name", identity_phone="01755555555")
    from app.services import cases as svc
    from tests.conftest import user_by_role

    sup = user_by_role("supervisor")
    svc.assess_severity(case, sup, 3, "Daily threats and coercion; credible risk of image-based abuse.")
    svc.add_note(case, sup, "Internal note: reporter lives near the market.")
    client.post("/track/", data={"reference": case.reference, "secret": secret})
    r = client.get(f"/track/{case.reference}")
    for needle in (b"Hidden Name", b"01755555555", b"Internal note", b"Triage", b"Level 3"):
        assert needle not in r.data, needle


def test_reporter_message_and_forget_device(client):
    case, secret = make_case()
    client.post("/track/", data={"reference": case.reference, "secret": secret})
    r = client.post(f"/track/{case.reference}/message", data={"body": "Is there any update? I am worried."})
    assert r.status_code == 302 and any(u.kind == "reporter_message" for u in case.updates)
    client.post(f"/track/{case.reference}/forget")
    assert client.get(f"/track/{case.reference}").status_code == 403


def test_phone_number_typed_in_bangla_digits_is_accepted(client):
    walk_report(
        client,
        {4: {"submission_type": "confidential", "identity_phone": "০১৭১২৩৪৫৬৭৮", "contact_preference": "phone", "consent_contact": "y"}},
    )
    case = Case.query.order_by(Case.id.desc()).first()
    assert case.identity.read_payload()["phone"] == "01712345678"


def test_second_report_after_submitting_creates_a_second_case(client):
    """Regression: a new report started before dismissing the receipt must not reuse the submitted draft."""
    walk_report(client)
    first = client.get("/report/received").data.decode().split('id="ref">')[1].split("<")[0]
    r = walk_report(client, {3: {"narrative": "A second, different incident at the market last night."}})
    assert r.status_code == 302 and r.headers["Location"].endswith("/report/received")
    assert Case.query.count() == SEEDED + 2
    second = client.get("/report/received").data.decode().split('id="ref">')[1].split("<")[0]
    assert second != first
    assert Case.query.filter_by(reference=second).one().narrative.startswith("A second")


def test_anonymous_reporting_and_tracking_store_no_ip_link(client):
    walk_report(client)
    case = Case.query.order_by(Case.id.desc()).first()
    events = AuditEvent.query.filter(AuditEvent.case_id == case.id).all()
    assert events and all(e.ip_hash is None for e in events)
    page = client.get("/report/received").data.decode()
    secret = page.split('id="secret">')[1].split("<")[0]
    client.post("/track/", data={"reference": case.reference, "secret": secret})
    assert AuditEvent.query.filter_by(event_type="track.opened").one().ip_hash is None
    client.post("/auth/login", data={"email": "nobody@example.org", "password": "wrong-password-12"})
    assert AuditEvent.query.filter_by(event_type="auth.login_failed").one().ip_hash is not None


def test_expired_drafts_are_purged_when_anyone_uses_the_form(client, app):
    from app.services import drafts as draft_service

    other = app.test_client()
    other.post("/report/1", data={"category": "other"})
    ReportDraft.query.one().expires_at = utcnow().replace(year=2000)
    db.session.commit()
    draft_service._last_purge = 0.0
    client.get("/report/1")
    assert ReportDraft.query.count() == 0


def test_stuck_submitting_drafts_are_purged(client):
    client.post("/report/1", data={"category": "other"})
    row = ReportDraft.query.one()
    row.status = "submitting"
    row.expires_at = utcnow().replace(year=2000)
    db.session.commit()
    assert drafts.purge_expired() == 1


def test_identity_fields_work_without_javascript(client):
    html = client.get("/report/4").data.decode()
    assert "data-identity-fields hidden" not in html and 'name="identity_name"' in html
