from app import db
from app.models import Case, ModerationAppeal, ModerationFlag, PublicRequest
from tests.conftest import case_by_text, login


def test_public_request_flow_and_contact_encryption(client):
    r = client.post(
        "/requests/new",
        data={
            "request_type": "correction",
            "publication_slug": "recognising-online-blackmail-and-what-to-do-first",
            "message": "The guide says to block first but reporting first preserves evidence; please clarify.",
            "contact": "me@example.org",
        },
    )
    assert r.status_code == 200 and b"RQ-" in r.data
    req = PublicRequest.query.one()
    assert req.publication is not None and b"me@example.org" not in req.contact_enc
    login(client, "editorial")
    r = client.get("/workspace/requests")
    assert req.reference.encode() in r.data
    r = client.get(f"/workspace/requests/{req.id}")
    assert b"me@example.org" not in r.data
    r = client.get(f"/workspace/requests/{req.id}?reveal=1")
    assert b"me@example.org" in r.data
    from app.models import AuditEvent

    assert AuditEvent.query.filter_by(event_type="request.contact_revealed").count() == 1
    r = client.post(f"/workspace/requests/{req.id}", data={"status": "upheld", "resolution": "Clarification added to the guide."})
    assert r.status_code == 302 and PublicRequest.query.one().status == "upheld"


def test_public_request_honeypot_and_complaint_routing(client):
    r = client.post(
        "/requests/new",
        data={
            "request_type": "complaint",
            "message": "A complaint about how my case was handled by the team, long enough.",
            "website": "x",
        },
    )
    assert r.status_code == 200 and PublicRequest.query.count() == 0
    client.post(
        "/requests/new",
        data={"request_type": "complaint", "message": "A complaint about how my case was handled by the team, long enough."},
    )
    login(client, "editorial")  # editorial handles corrections but not complaints
    assert PublicRequest.query.one().reference.encode() not in client.get("/workspace/requests").data
    client.post("/auth/logout")
    login(client, "moderator")
    assert PublicRequest.query.one().reference.encode() in client.get("/workspace/requests").data


def test_flag_hold_and_appeal_by_different_moderator(client):
    case = case_by_text("Relief goods")
    login(client, "editorial")
    r = client.post(
        f"/workspace/cases/{case.reference}/flag",
        data={
            "target_type": "case",
            "target_id": case.id,
            "reason": "fabrication_suspected",
            "notes": "Documents look edited; needs a moderator's eyes.",
        },
    )
    assert r.status_code == 302 and ModerationFlag.query.count() == 1
    client.post("/auth/logout")
    login(client, "moderator")
    flag = ModerationFlag.query.one()
    r = client.post(
        f"/workspace/moderation/flags/{flag.id}",
        data={"decision": "actioned", "action_taken": "Held pending verification.", "hold_case": "y"},
    )
    assert r.status_code == 302 and Case.query.get(case.id).moderation_hold is True
    appeal = ModerationAppeal(flag_id=flag.id, reference="AP-TEST-0001", message="The documents are originals; please review again.")
    db.session.add(appeal)
    db.session.commit()
    r = client.post(f"/workspace/moderation/appeals/{appeal.id}", data={"decision": "upheld", "notes": "Same moderator must not decide."})
    assert r.status_code == 302 and appeal.status == "open"
    # a different moderator can decide
    from app.models import User

    other = User(email="mod2@helplagbe.local", name="Second Moderator", role="moderator")
    other.set_password("demo-password-2026")
    db.session.add(other)
    db.session.commit()
    client.post("/auth/logout")
    import pyotp

    from tests.conftest import TOTP_SECRET, enrol_mfa

    enrol_mfa(other)
    client.post("/auth/login", data={"email": other.email, "password": "demo-password-2026"})
    client.post("/auth/mfa/verify", data={"code": pyotp.TOTP(TOTP_SECRET).now()})
    r = client.post(f"/workspace/moderation/appeals/{appeal.id}", data={"decision": "upheld", "notes": "Originals verified; hold lifted."})
    assert appeal.status == "upheld" and Case.query.get(case.id).moderation_hold is False
