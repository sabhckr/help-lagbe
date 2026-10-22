"""Encryption helpers for the separate identity store.

Identity payloads (name, phone, email, safe-contact notes) are encrypted with Fernet
(AES-128-CBC + HMAC) using IDENTITY_ENCRYPTION_KEY. The key never touches the database.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

log = logging.getLogger(__name__)


def _fernet() -> Fernet:
    key = current_app.config.get("IDENTITY_ENCRYPTION_KEY") or ""
    if not key:
        if current_app.config.get("ENV_NAME") == "production":
            raise RuntimeError("IDENTITY_ENCRYPTION_KEY is not configured")
        # Development only: derive a stable key from SECRET_KEY so local data survives restarts.
        derived = hashlib.sha256(("identity:" + current_app.config["SECRET_KEY"]).encode()).digest()
        key = base64.urlsafe_b64encode(derived).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_json(payload: dict[str, Any]) -> bytes:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _fernet().encrypt(data)


def decrypt_json(token: bytes | None) -> dict[str, Any]:
    if not token:
        return {}
    try:
        return json.loads(_fernet().decrypt(token).decode("utf-8"))
    except (InvalidToken, ValueError):
        log.error("identity payload could not be decrypted (wrong key?)")
        return {"_error": "undecryptable"}


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_secret(secret: str) -> str:
    """Hash a tracking secret. SHA-256 over a high-entropy random secret is adequate here;
    secrets are 12+ random characters, not user-chosen passwords."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()
