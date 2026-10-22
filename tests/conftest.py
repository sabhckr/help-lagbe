"""Shared fixtures. Every test gets a fresh in-memory database seeded with the fictional demo data."""

from __future__ import annotations

import pyotp
import pytest

from app import create_app, db
from app.models import Case, User
from app.seed import DEMO_PASSWORD, seed_demo
from app.services import cases as case_service
from app.services.security import store_mfa_secret

TOTP_SECRET = pyotp.random_base32()


@pytest.fixture
def app(tmp_path):
    application = create_app("testing", {"EVIDENCE_DIR": str(tmp_path / "evidence")})
    with application.app_context():
        seed_demo()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def user_by_role(role: str) -> User:
    user = User.query.filter_by(role=role).first()
    assert user is not None, role
    return user


def enrol_mfa(user: User) -> None:
    store_mfa_secret(user, TOTP_SECRET)
    user.mfa_enabled = True
    db.session.commit()


def login(client, role: str, *, enrol: bool = True):
    """Log in through the real form, completing MFA for staff roles."""
    user = user_by_role(role)
    if enrol and user.is_privileged:
        enrol_mfa(user)
    r = client.post("/auth/login", data={"email": user.email, "password": DEMO_PASSWORD})
    assert r.status_code == 302, r.data[:200]
    if user.is_privileged:
        assert r.headers["Location"].endswith("/auth/mfa/verify"), r.headers["Location"]
        r = client.post("/auth/mfa/verify", data={"code": pyotp.TOTP(TOTP_SECRET).now()})
        assert r.status_code == 302, r.data[:200]
    return user


BASE_REPORT = {
    "category": "blackmail",
    "title": "Someone is threatening to share my photos",
    "narrative": "A person I met online says they will send private pictures to my family unless I pay them money every week.",
    "immediate_danger": "unsure",
    "submission_type": "anonymous",
    "consent_process": "y",
}


def make_case(**overrides) -> tuple[Case, str]:
    data = {**BASE_REPORT, **overrides}
    data["consent_process"] = bool(data.get("consent_process"))
    return case_service.create_case(data)
