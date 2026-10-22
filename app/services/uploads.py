"""Evidence uploads: allow-listed types verified by magic bytes, size limits, random storage
names outside the web root, SHA-256 hashing, optional ClamAV scan, reason-gated downloads."""

from __future__ import annotations

import os
import re
import socket
import uuid
from pathlib import Path

from flask import current_app
from werkzeug.datastructures import FileStorage

from app import permissions as P
from app.crypto import sha256_hex
from app.extensions import db
from app.models.base import utcnow
from app.models.case import Case
from app.models.evidence import (
    SCAN_CLEAN,
    SCAN_ERROR,
    SCAN_INFECTED,
    SCAN_NOT_SCANNED,
    CustodyRecord,
    Evidence,
)
from app.services import access, audit


class UploadError(ValueError):
    pass


# (extension, mime, magic prefixes)
_SIGNATURES: dict[str, tuple[str, tuple[bytes, ...]]] = {
    "jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    "jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    "png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    "webp": ("image/webp", (b"RIFF",)),
    "pdf": ("application/pdf", (b"%PDF-",)),
    "mp3": ("audio/mpeg", (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")),
    "m4a": ("audio/mp4", (b"ftyp",)),
    "mp4": ("video/mp4", (b"ftyp",)),
    "txt": ("text/plain", ()),
}


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _sniff_ok(ext: str, head: bytes) -> bool:
    mime, prefixes = _SIGNATURES[ext]
    if ext in ("m4a", "mp4"):
        return head[4:8] == b"ftyp"
    if ext == "webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if ext == "txt":
        try:
            head.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return b"\x00" not in head
    return any(head.startswith(p) for p in prefixes)


def _safe_original_name(name: str) -> str:
    name = os.path.basename(name or "file")
    name = re.sub(r"[^\w.\- ()ঀ-৿]", "_", name)[:200]
    return name or "file"


def evidence_root() -> Path:
    root = Path(current_app.config["EVIDENCE_DIR"] or (Path(current_app.instance_path) / "evidence"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def scan_file(path: Path) -> tuple[str, str | None]:
    """Scan with clamd over a UNIX socket when CLAMD_SOCKET is configured; otherwise report
    honestly that the file was not scanned."""
    sock_path = current_app.config.get("CLAMD_SOCKET")
    if not sock_path:
        return SCAN_NOT_SCANNED, "scanner not configured"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(20)
            s.connect(sock_path)
            s.sendall(b"zINSTREAM\0")
            with path.open("rb") as fh:
                while chunk := fh.read(65536):
                    s.sendall(len(chunk).to_bytes(4, "big") + chunk)
            s.sendall(b"\0\0\0\0")
            reply = s.recv(4096).decode(errors="replace").strip()
    except OSError as exc:
        return SCAN_ERROR, f"scanner error: {exc.__class__.__name__}"
    if reply.endswith("OK"):
        return SCAN_CLEAN, None
    if "FOUND" in reply:
        return SCAN_INFECTED, reply[-120:]
    return SCAN_ERROR, reply[-120:]


def store_evidence(case: Case, file: FileStorage, *, description: str | None = None, uploaded_by=None) -> Evidence:
    cfg = current_app.config
    if not file or not file.filename:
        raise UploadError("upload.error_empty")
    ext = _ext(file.filename)
    if ext not in cfg["EVIDENCE_ALLOWED_EXTENSIONS"] or ext not in _SIGNATURES:
        raise UploadError("upload.error_type")
    head = file.stream.read(16)
    file.stream.seek(0)
    if not _sniff_ok(ext, head):
        raise UploadError("upload.error_type")
    existing = Evidence.query.filter_by(case_id=case.id).filter(Evidence.deleted_at.is_(None)).count()
    if existing >= cfg["EVIDENCE_MAX_FILES_PER_REPORT"]:
        raise UploadError("upload.error_count")

    case_dir = evidence_root() / case.reference
    case_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    target = case_dir / stored_name
    size = 0
    hasher_chunks: list[bytes] = []
    max_bytes = cfg["MAX_CONTENT_LENGTH"]
    with target.open("wb") as out:
        while chunk := file.stream.read(1024 * 256):
            size += len(chunk)
            if size > max_bytes:
                out.close()
                target.unlink(missing_ok=True)
                raise UploadError("upload.error_size")
            out.write(chunk)
            hasher_chunks.append(chunk)
    if size == 0:
        target.unlink(missing_ok=True)
        raise UploadError("upload.error_empty")
    digest = sha256_hex(b"".join(hasher_chunks))
    os.chmod(target, 0o600)
    scan_status, scan_detail = scan_file(target)

    evidence = Evidence(
        case_id=case.id,
        stored_name=stored_name,
        original_name=_safe_original_name(file.filename),
        mime_type=_SIGNATURES[ext][0],
        size_bytes=size,
        sha256=digest,
        description=(description or "").strip() or None,
        scan_status=scan_status,
        scan_detail=scan_detail,
        uploaded_by_reporter=uploaded_by is None,
        uploaded_by_user_id=getattr(uploaded_by, "id", None),
        quarantined=(scan_status == SCAN_INFECTED),
    )
    db.session.add(evidence)
    db.session.flush()
    db.session.add(
        CustodyRecord(
            evidence_id=evidence.id,
            actor_id=getattr(uploaded_by, "id", None),
            action="received",
            hash_at_time=digest,
            notes=f"scan={scan_status}",
        )
    )
    audit.record(
        "evidence.received",
        actor=uploaded_by,
        target_type="evidence",
        target_id=evidence.id,
        case_id=case.id,
        details={"ext": ext, "size": size, "scan": scan_status},
    )
    return evidence


def evidence_path(evidence: Evidence) -> Path:
    return evidence_root() / evidence.case.reference / evidence.stored_name


def authorize_download(evidence: Evidence, user, reason: str, *, export: bool = False) -> Path:
    """Check permission + assignment + reason, log, and return the file path."""
    reason = (reason or "").strip()
    perm = P.CASE_EVIDENCE_EXPORT if export else P.CASE_EVIDENCE_DOWNLOAD
    allowed = user.can(perm) and access.can_view_narrative(user, evidence.case) and evidence.is_available
    if not allowed or len(reason) < 10:
        audit.record(
            "evidence.download_refused",
            actor=user,
            target_type="evidence",
            target_id=evidence.id,
            case_id=evidence.case_id,
            reason=reason or None,
            details={"export": export},
            commit=True,
        )
        raise PermissionError("evidence.error_denied")
    path = evidence_path(evidence)
    if not path.exists():
        raise FileNotFoundError
    db.session.add(
        CustodyRecord(
            evidence_id=evidence.id,
            actor_id=user.id,
            action="exported" if export else "accessed",
            hash_at_time=evidence.sha256,
            notes=reason,
        )
    )
    audit.record(
        "evidence.export" if export else "evidence.download",
        actor=user,
        target_type="evidence",
        target_id=evidence.id,
        case_id=evidence.case_id,
        reason=reason,
    )
    db.session.commit()
    return path


def verify_hash(evidence: Evidence, user) -> bool:
    path = evidence_path(evidence)
    if not path.exists():
        return False
    digest = sha256_hex(path.read_bytes())
    ok = digest == evidence.sha256
    db.session.add(
        CustodyRecord(
            evidence_id=evidence.id, actor_id=user.id, action="hash_verified", hash_at_time=digest, notes="match" if ok else "MISMATCH"
        )
    )
    audit.record(
        "evidence.hash_verified", actor=user, target_type="evidence", target_id=evidence.id, case_id=evidence.case_id, details={"match": ok}
    )
    db.session.commit()
    return ok


def soft_delete(evidence: Evidence, user, reason: str) -> None:
    evidence.deleted_at = utcnow()
    db.session.add(CustodyRecord(evidence_id=evidence.id, actor_id=user.id, action="deleted", notes=reason))
    audit.record("evidence.deleted", actor=user, target_type="evidence", target_id=evidence.id, case_id=evidence.case_id, reason=reason)
    db.session.commit()
