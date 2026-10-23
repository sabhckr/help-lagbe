"""Reporting drafts: encrypted, server-side progress that survives reloads and language switches.

A draft is found through a random token held in the browser session. The token itself is never
placed in a URL. Answers and uploaded files are encrypted at rest. Submission claims the draft
atomically so a double click cannot create two cases, and the one-time tracking key is kept only
inside the encrypted draft until the reporter confirms they have saved it.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import uuid
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

from flask import session
from sqlalchemy import update
from werkzeug.datastructures import FileStorage

from app import report_steps
from app.crypto import decrypt_bytes, decrypt_json, encrypt_bytes, encrypt_json, sha256_hex
from app.extensions import db
from app.i18n import get_locale
from app.models.base import utcnow
from app.models.draft import DRAFT_OPEN, DRAFT_SUBMITTED, DRAFT_SUBMITTING, DraftFile, ReportDraft
from app.services import uploads
from app.services.cases import create_case
from app.services.uploads import UploadError

SESSION_KEY = "report_draft"
DRAFT_HOURS = 24
RECEIPT_HOURS = 2


class DraftError(ValueError):
    """Carries a translation key that can be shown to the reporter."""


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _dir(row: ReportDraft) -> Path:
    return Path(uploads.evidence_root()) / "drafts" / str(row.id)


def current() -> ReportDraft | None:
    token = session.get(SESSION_KEY)
    if not token:
        return None
    row = ReportDraft.query.filter_by(token_hash=_hash(token)).first()
    if row is None:
        session.pop(SESSION_KEY, None)
        return None
    if row.expires_at < utcnow() and row.status != DRAFT_SUBMITTING:
        delete(row)
        session.pop(SESSION_KEY, None)
        return None
    return row


def start() -> ReportDraft:
    token = secrets.token_urlsafe(32)
    row = ReportDraft(
        token_hash=_hash(token),
        status=DRAFT_OPEN,
        payload_enc=encrypt_json({}),
        expires_at=utcnow() + timedelta(hours=DRAFT_HOURS),
    )
    db.session.add(row)
    db.session.commit()
    session[SESSION_KEY] = token
    return row


def data(row: ReportDraft | None) -> dict[str, Any]:
    if row is None or not row.payload_enc:
        return {}
    values = decrypt_json(row.payload_enc)
    return {} if "_error" in values else values


def save(row: ReportDraft, values: dict[str, Any]) -> None:
    merged = data(row)
    merged.update(values)
    row.payload_enc = encrypt_json(merged)
    row.expires_at = utcnow() + timedelta(hours=DRAFT_HOURS)
    db.session.commit()


def add_files(row: ReportDraft, files: list[FileStorage]) -> list[tuple[str, str]]:
    """Validate and store uploads encrypted. Returns (filename, error key) for each refusal."""
    refusals: list[tuple[str, str]] = []
    existing = DraftFile.query.filter_by(draft_id=row.id).count()
    limit = current_limit()
    folder = _dir(row)
    for upload in files:
        if not upload or not upload.filename:
            continue
        if existing >= limit:
            refusals.append((upload.filename, "upload.error_count"))
            continue
        try:
            ext, raw = uploads.read_validated(upload)
        except UploadError as exc:
            refusals.append((upload.filename, str(exc)))
            continue
        folder.mkdir(parents=True, exist_ok=True)
        stored = f"{uuid.uuid4().hex}.bin"
        target = folder / stored
        target.write_bytes(encrypt_bytes(raw))
        os.chmod(target, 0o600)
        db.session.add(
            DraftFile(
                draft_id=row.id,
                stored_name=stored,
                original_name=uploads.safe_original_name(upload.filename),
                mime_type=uploads.mime_for(ext),
                size_bytes=len(raw),
                sha256=sha256_hex(raw),
            )
        )
        existing += 1
    row.expires_at = utcnow() + timedelta(hours=DRAFT_HOURS)
    db.session.commit()
    return refusals


def current_limit() -> int:
    from flask import current_app

    return int(current_app.config["EVIDENCE_MAX_FILES_PER_REPORT"])


def remove_file(row: ReportDraft, file_id: int) -> bool:
    item = DraftFile.query.filter_by(id=file_id, draft_id=row.id).first()
    if item is None:
        return False
    (_dir(row) / item.stored_name).unlink(missing_ok=True)
    db.session.delete(item)
    db.session.commit()
    return True


def _claim(row: ReportDraft) -> bool:
    result = db.session.execute(
        update(ReportDraft).where(ReportDraft.id == row.id, ReportDraft.status == DRAFT_OPEN).values(status=DRAFT_SUBMITTING)
    )
    db.session.commit()
    return getattr(result, "rowcount", 0) == 1


def _release(row_id: int) -> None:
    db.session.execute(
        update(ReportDraft).where(ReportDraft.id == row_id, ReportDraft.status == DRAFT_SUBMITTING).values(status=DRAFT_OPEN)
    )
    db.session.commit()


def submit(row: ReportDraft, reporter_user=None) -> None:
    """Create the case, move the uploads into it, and keep the receipt until the reporter dismisses it.

    Raises DraftError with a translation key when the report cannot be sent.
    """
    if row.status == DRAFT_SUBMITTED:
        return
    values = data(row)
    missing = report_steps.first_incomplete(values)
    if missing is not None:
        raise DraftError("report.error_incomplete")
    if not _claim(row):
        raise DraftError("report.error_busy")
    row_id = row.id
    try:
        case, secret = create_case(report_steps.case_data(values), reporter_user=reporter_user, language=get_locale(), commit=False)
        for item in list(row.files):
            raw = decrypt_bytes((_dir(row) / item.stored_name).read_bytes())
            uploads.store_evidence(
                case,
                FileStorage(stream=BytesIO(raw), filename=item.original_name, content_type=item.mime_type),
                description=None,
                uploaded_by=None,
            )
        row.status = DRAFT_SUBMITTED
        row.case_id = case.id
        row.payload_enc = None
        row.receipt_enc = encrypt_json({"reference": case.reference, "secret": secret, "safety": bool(case.safety_flag)})
        row.expires_at = utcnow() + timedelta(hours=RECEIPT_HOURS)
        for item in list(row.files):
            db.session.delete(item)
        db.session.commit()
    except Exception:
        db.session.rollback()
        _release(row_id)
        raise
    shutil.rmtree(_dir(row), ignore_errors=True)


def receipt(row: ReportDraft | None) -> dict[str, Any] | None:
    if row is None or row.status != DRAFT_SUBMITTED or not row.receipt_enc:
        return None
    values = decrypt_json(row.receipt_enc)
    return None if "_error" in values else values


def dismiss(row: ReportDraft) -> None:
    row.receipt_enc = None
    db.session.commit()
    session.pop(SESSION_KEY, None)


def delete(row: ReportDraft) -> None:
    folder = _dir(row)
    db.session.delete(row)
    db.session.commit()
    shutil.rmtree(folder, ignore_errors=True)


def purge_expired() -> int:
    stale = ReportDraft.query.filter(ReportDraft.expires_at < utcnow(), ReportDraft.status != DRAFT_SUBMITTING).all()
    for row in stale:
        delete(row)
    return len(stale)
