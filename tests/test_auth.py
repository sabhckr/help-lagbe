import pyotp

from app import db
from app.models import AuditEvent, User
from app.seed import DEMO_PASSWORD
from tests.conftest import enrol_mfa, login, user_by_role


def test_login_page_renders(client):
    r = client.get("/auth/login")
    assert r.status_code == 200
    assert b"csrf-token" in r.data


def test_wrong_password_is_generic_and_logged(client, app):
    r = client.post("/auth/login", data={"email": "admin@helplagbe.local", "password": "nope-nope-nope"})
    assert r.status_code == 200
    assert b"not correct" in r.data
    assert AuditEvent.query.filter_by(event_type="auth.login_failed").count() == 1


def test_unknown_email_same_response_as_wrong_password(client):
    r1 = client.post("/auth/login", data={"email": "nobody@helplagbe.local", "password": "x" * 12})
    r2 = client.post("/auth/login", data={"email": "admin@helplagbe.local", "password": "x" * 12})
    assert r1.status_code == r2.status_code == 200
    assert b"not correct" in r1.data and b"not correct" in r2.data


def test_lockout_after_repeated_failures(client, app):
    for _ in range(app.config["LOGIN_MAX_FAILURES"]):
        client.post("/auth/login", data={"email": "support@helplagbe.local", "password": "wrong-password-1"})
    user = user_by_role("support")
    assert user.is_locked()
    # even the right password is refused while locked
    r = client.post("/auth/login", data={"email": user.email, "password": DEMO_PASSWORD})
    assert r.status_code == 200 and b"not correct" in r.data


def test_staff_must_enrol_mfa_before_workspace(client):
    user = user_by_role("legal")
    r = client.post("/auth/login", data={"email": user.email, "password": DEMO_PASSWORD})
    assert r.status_code == 302 and r.headers["Location"].endswith("/auth/mfa/setup")
    # not logged in yet: the workspace is still closed
    assert client.get("/workspace/").status_code == 302
    r = client.get("/auth/mfa/setup")
    assert r.status_code == 200 and b"data:image/svg+xml" in r.data
    with client.session_transaction() as sess:
        secret = sess["mfa_setup_secret"]
    r = client.post("/auth/mfa/setup", data={"code": "000000"})
    assert b"not valid" in r.data
    r = client.post("/auth/mfa/setup", data={"code": pyotp.TOTP(secret).now()})
    assert r.status_code == 302
    assert client.get("/workspace/").status_code == 200
    assert user_by_role("legal").mfa_enabled is True


def test_mfa_verify_rejects_wrong_code_and_locks_after_five(client):
    user = user_by_role("cyber")
    enrol_mfa(user)
    client.post("/auth/login", data={"email": user.email, "password": DEMO_PASSWORD})
    for _ in range(4):
        r = client.post("/auth/mfa/verify", data={"code": "123456"})
        assert b"not valid" in r.data
    r = client.post("/auth/mfa/verify", data={"code": "123456"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/auth/login")
    assert client.get("/workspace/").status_code == 302


def test_full_mfa_login_and_logout(client):
    login(client, "support")
    assert client.get("/workspace/").status_code == 200
    r = client.post("/auth/logout")
    assert r.status_code == 302
    assert client.get("/workspace/").status_code == 302


def test_reporter_does_not_need_mfa(client):
    login(client, "reporter")
    assert client.get("/my-reports").status_code == 200
    assert client.get("/workspace/").status_code == 403


def test_open_redirect_is_blocked(client):
    user = user_by_role("reporter")
    r = client.post("/auth/login?next=https://evil.example/phish", data={"email": user.email, "password": DEMO_PASSWORD})
    assert r.status_code == 302
    assert "evil.example" not in r.headers["Location"]
    r = client.get("/lang/bn?next=//evil.example")
    assert "evil.example" not in r.headers["Location"]


def test_registration_password_policy_and_no_enumeration(client):
    r = client.post(
        "/auth/register", data={"name": "Test Person", "email": "new@example.org", "password": "short", "password2": "short", "accept": "y"}
    )
    assert r.status_code == 200 and b"at least 12" in r.data
    r = client.post(
        "/auth/register",
        data={
            "name": "Test Person",
            "email": "new@example.org",
            "password": "a-long-enough-pass-1",
            "password2": "a-long-enough-pass-1",
            "accept": "y",
        },
    )
    assert r.status_code == 302
    assert User.query.filter_by(email="new@example.org").one().role == "reporter"
    # registering the same email again gives the same redirect + message, not an "exists" error
    r = client.post(
        "/auth/register",
        data={
            "name": "Other",
            "email": "new@example.org",
            "password": "another-long-pass-2",
            "password2": "another-long-pass-2",
            "accept": "y",
        },
        follow_redirects=True,
    )
    assert b"This email is already registered" not in r.data and b"your account is ready" in r.data
    assert User.query.filter_by(email="new@example.org").count() == 1


def test_inactive_user_cannot_log_in(client):
    user = user_by_role("action")
    user.active = False
    db.session.commit()
    r = client.post("/auth/login", data={"email": user.email, "password": DEMO_PASSWORD})
    assert r.status_code == 200 and b"not correct" in r.data


def test_change_password_requires_current(client):
    login(client, "reporter")
    r = client.post(
        "/auth/password", data={"current": "wrong-current-pass", "password": "new-long-password-9", "password2": "new-long-password-9"}
    )
    assert b"not correct" in r.data
    r = client.post(
        "/auth/password", data={"current": DEMO_PASSWORD, "password": "new-long-password-9", "password2": "new-long-password-9"}
    )
    assert r.status_code == 302
    assert user_by_role("reporter").check_password("new-long-password-9")


def test_signed_in_people_can_sign_out_from_any_page(client):
    login(client, "support")
    assert b'action="/auth/logout"' in client.get("/workspace/").data
    assert b'action="/auth/logout"' in client.get("/").data
    client.post("/auth/logout")
    login(client, "reporter")
    page = client.get("/").data
    assert b'href="/my-reports"' in page and b'action="/auth/logout"' in page
