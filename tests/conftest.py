"""Shared fixtures. Every test gets a fresh in-memory database seeded with the fictional demo data."""

from __future__ import annotations

import os

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
    overrides = {"EVIDENCE_DIR": str(tmp_path / "evidence")}
    # Opt-in: run the same suite against a throwaway PostgreSQL database.
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        overrides.update({"SQLALCHEMY_DATABASE_URI": url, "SQLALCHEMY_ENGINE_OPTIONS": {"pool_pre_ping": False}})
    application = create_app("testing", overrides)
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
    "category": "threats_blackmail",
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


ANSWERS = {
    1: {"category": "threats_blackmail"},
    2: {"immediate_danger": "unsure"},
    3: {"narrative": "Someone keeps messaging me and says they will share my photos unless I pay.", "approximate_time": "Last week"},
    4: {"submission_type": "anonymous"},
    6: {"consent_process": "y"},
}


def walk_report(client, overrides: dict | None = None, *, submit: bool = True):
    """Go through the six reporting steps exactly as a browser would. Returns the final response."""
    overrides = overrides or {}
    response = None
    for step in (1, 2, 3, 4):
        data = {**ANSWERS[step], **overrides.get(step, {})}
        response = client.post(f"/report/{step}", data=data)
        assert response.status_code == 302, (step, response.status_code, response.data[:300])
    response = client.post("/report/5", data={"action": "continue"})
    assert response.status_code == 302
    if submit:
        response = client.post("/report/6", data={**ANSWERS[6], **overrides.get(6, {})})
    return response


def case_by_text(fragment: str) -> Case:
    """Seeded cases share categories, so tests pick them by a phrase in the narrative."""
    return Case.query.filter(Case.narrative.contains(fragment)).one()


def use_lang(client, lang: str) -> None:
    """Set the language cookie on the test server's domain (SERVER_NAME is localhost.test)."""
    client.set_cookie("hl_lang", lang, domain="localhost.test")
