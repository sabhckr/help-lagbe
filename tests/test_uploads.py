import io

from app.models import AuditEvent, Evidence
from app.services import uploads
from tests.conftest import login, user_by_role


def _case():
    from app.models import Case

    return Case.query.filter_by(category="threats_blackmail").one()  # assigned to support + cyber


def _upload(client, ref, name, content, ctype="multipart/form-data"):
    return client.post(
        f"/workspace/cases/{ref}/evidence", data={"file": (io.BytesIO(content), name), "description": "x"}, content_type=ctype
    )


def test_disallowed_extension_rejected(client):
    login(client, "cyber")
    r = _upload(client, _case().reference, "payload.exe", b"MZ" + b"\x00" * 50)
    assert r.status_code == 302 and Evidence.query.count() == 0


def test_mismatched_content_rejected(client):
    login(client, "cyber")
    r = _upload(client, _case().reference, "photo.png", b"<html><script>alert(1)</script></html>")
    assert r.status_code == 302 and Evidence.query.count() == 0


def test_valid_pdf_accepted_and_hashed(client, app):
    login(client, "cyber")
    r = _upload(client, _case().reference, "../../etc/passwd.pdf", b"%PDF-1.4\n%fake\n")
    assert r.status_code == 302
    ev = Evidence.query.one()
    assert ev.original_name == "passwd.pdf" and ev.mime_type == "application/pdf"
    assert ev.stored_name.endswith(".pdf") and "/" not in ev.stored_name
    assert len(ev.sha256) == 64 and ev.custody[0].action == "received"


def test_size_limit_enforced(client, app):
    login(client, "cyber")
    app.config["MAX_CONTENT_LENGTH"] = 2048
    r = _upload(client, _case().reference, "big.png", b"\x89PNG\r\n\x1a\n" + b"a" * 5000)
    assert r.status_code in (302, 413) and Evidence.query.count() == 0


def test_file_count_limit(client, app):
    login(client, "cyber")
    app.config["EVIDENCE_MAX_FILES_PER_REPORT"] = 1
    _upload(client, _case().reference, "a.txt", b"hello world")
    _upload(client, _case().reference, "b.txt", b"hello again")
    assert Evidence.query.count() == 1


def test_download_needs_permission_assignment_and_reason(client):
    login(client, "cyber")
    ref = _case().reference
    _upload(client, ref, "a.txt", b"hello world")
    ev = Evidence.query.one()
    r = client.post(f"/workspace/cases/{ref}/evidence/{ev.id}/download", data={"reason": "short"})
    assert r.status_code == 302 and AuditEvent.query.filter_by(event_type="evidence.download").count() == 0
    r = client.post(
        f"/workspace/cases/{ref}/evidence/{ev.id}/download", data={"reason": "Reviewing the screenshot for the platform report."}
    )
    assert r.status_code == 200 and r.data == b"hello world"
    assert "attachment" in r.headers["Content-Disposition"]
    log = AuditEvent.query.filter_by(event_type="evidence.download").one()
    assert log.actor_role == "cyber" and log.case_id == _case().id and "platform report" in log.reason
    assert any(c.action == "accessed" for c in ev.custody)
    # GET never serves files
    assert client.get(f"/workspace/cases/{ref}/evidence/{ev.id}/download").status_code == 405
    client.post("/auth/logout")
    # support is assigned but lacks the download permission
    login(client, "support")
    r = client.post(f"/workspace/cases/{ref}/evidence/{ev.id}/download", data={"reason": "I want to look at the evidence file."})
    assert r.status_code == 403
    client.post("/auth/logout")
    # editorial is not assigned at all
    login(client, "editorial")
    r = client.post(f"/workspace/cases/{ref}/evidence/{ev.id}/download", data={"reason": "I want to look at the evidence file."})
    assert r.status_code == 403


def test_export_is_restricted_and_logged(client):
    login(client, "cyber")
    ref = _case().reference
    _upload(client, ref, "a.txt", b"hello world")
    ev = Evidence.query.one()
    r = client.post(
        f"/workspace/cases/{ref}/evidence/{ev.id}/download",
        data={"reason": "Export for the lawyer as agreed with reporter.", "export": "1"},
    )
    assert r.status_code == 403  # cyber cannot export
    client.post("/auth/logout")
    login(client, "legal")
    from app.services import cases as svc

    svc.assign(_case(), user_by_role("supervisor"), user_by_role("legal"))
    r = client.post(
        f"/workspace/cases/{ref}/evidence/{ev.id}/download",
        data={"reason": "Export for the lawyer as agreed with reporter.", "export": "1"},
    )
    assert r.status_code == 200
    assert AuditEvent.query.filter_by(event_type="evidence.export").count() == 1


def test_hash_verification_detects_tampering(client, app):
    login(client, "cyber")
    ref = _case().reference
    _upload(client, ref, "a.txt", b"hello world")
    ev = Evidence.query.one()
    assert uploads.verify_hash(ev, user_by_role("cyber")) is True
    from app.crypto import encrypt_bytes

    ev.data_enc = encrypt_bytes(b"tampered")
    assert uploads.verify_hash(ev, user_by_role("cyber")) is False
    assert any(c.notes == "MISMATCH" for c in ev.custody)


def test_evidence_not_served_from_static(client, app):
    login(client, "cyber")
    ref = _case().reference
    _upload(client, ref, "a.txt", b"hello world")
    ev = Evidence.query.one()
    assert client.get(f"/static/evidence/{ref}/{ev.stored_name}").status_code == 404


def test_evidence_is_encrypted_in_the_database_and_not_written_to_disk(client, app):
    login(client, "cyber")
    ref = _case().reference
    _upload(client, ref, "a.txt", b"PLAINTEXT-EVIDENCE-MARKER")
    ev = Evidence.query.one()
    assert ev.data_enc is not None and b"PLAINTEXT-EVIDENCE-MARKER" not in ev.data_enc
    root = uploads.evidence_root()
    assert not root.exists() or not any(p.is_file() for p in root.rglob("*"))
    r = client.post(f"/workspace/cases/{ref}/evidence/{ev.id}/download", data={"reason": "Checking the uploaded text for the case file."})
    assert r.status_code == 200 and r.data == b"PLAINTEXT-EVIDENCE-MARKER"


def test_older_evidence_on_disk_still_downloads(client, app):
    """Records made before database storage keep working: contents are read from the old disk path."""
    from app import db

    login(client, "cyber")
    case = _case()
    ev = Evidence(
        case_id=case.id,
        stored_name="legacy.txt",
        original_name="legacy.txt",
        mime_type="text/plain",
        size_bytes=11,
        sha256="0" * 64,
        scan_status="not_scanned",
    )
    db.session.add(ev)
    db.session.commit()
    path = uploads.evidence_path(ev)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"legacy body")
    r = client.post(f"/workspace/cases/{case.reference}/evidence/{ev.id}/download", data={"reason": "Reading an older file kept on disk."})
    assert r.status_code == 200 and r.data == b"legacy body"
