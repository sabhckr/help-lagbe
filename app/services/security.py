"""Security helpers: safe redirects, password policy, MFA, session hygiene."""

from __future__ import annotations

import re
import secrets
from urllib.parse import urljoin, urlparse

import pyotp
from flask import current_app, request, session

from app.crypto import decrypt_json, encrypt_json

_COMMON_PASSWORDS = {
    "password",
    "password1",
    "123456789012",
    "qwertyuiop12",
    "helplagbe123",
    "admin1234567",
    "welcome12345",
    "letmein12345",
    "iloveyou1234",
}


def is_safe_url(target: str | None) -> bool:
    """Only allow redirects to paths on this host (prevents the open redirect found in the audit)."""
    if not target:
        return False
    if target.startswith("//") or "\\" in target:
        return False
    ref = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ("http", "https") and ref.netloc == test.netloc


def safe_next(default: str) -> str:
    target = request.args.get("next") or request.form.get("next")
    return target if target and is_safe_url(target) else default


def password_problems(password: str, *, email: str = "", name: str = "") -> list[str]:
    """Return a list of translation keys describing why the password is unacceptable."""
    problems: list[str] = []
    min_len = current_app.config.get("PASSWORD_MIN_LENGTH", 12)
    if len(password) < min_len:
        problems.append("validation.password_length")
    if password.lower() in _COMMON_PASSWORDS or re.fullmatch(r"(.)\1{7,}", password):
        problems.append("validation.password_common")
    local = (email or "").split("@")[0].lower()
    if local and len(local) >= 4 and local in password.lower():
        problems.append("validation.password_contains_email")
    if name and len(name) >= 4 and name.lower() in password.lower():
        problems.append("validation.password_contains_name")
    return problems


# ---- MFA (TOTP) ---------------------------------------------------------------------------
def new_mfa_secret() -> str:
    return pyotp.random_base32()


def store_mfa_secret(user, secret: str) -> None:
    user.mfa_secret_enc = encrypt_json({"s": secret}).decode("ascii")


def load_mfa_secret(user) -> str | None:
    if not user.mfa_secret_enc:
        return None
    return decrypt_json(user.mfa_secret_enc.encode("ascii")).get("s")


def provisioning_uri(user, secret: str) -> str:
    issuer = current_app.config.get("SITE_NAME", "Help Lagbe?")
    return pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    code = re.sub(r"\D", "", code or "")
    if len(code) != 6:
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def mfa_required_for(user) -> bool:
    return bool(current_app.config.get("MFA_REQUIRED_FOR_STAFF", True)) and user.is_privileged


# ---- Sessions -----------------------------------------------------------------------------
def reset_session_keep_locale() -> None:
    """Clear the session on login/logout to prevent fixation; keep only harmless prefs."""
    keep = {k: session[k] for k in ("_csrf_token", "csrf_token") if k in session}
    session.clear()
    session.update(keep)


def new_session_token() -> str:
    return secrets.token_hex(16)
