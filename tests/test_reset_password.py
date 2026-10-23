"""The reset-password command: the recovery path when a staff member, or the only admin, forgets a password."""

from datetime import timedelta

from app import db
from app.models import User
from app.models.audit import SENSITIVE_EVENTS, AuditEvent
from app.models.base import utcnow
from app.seed import DEMO_PASSWORD
from tests.conftest import enrol_mfa, user_by_role

NEW_PASSWORD = "quiet-lantern-harbour-9"
REASON = "Owner forgot the admin password"


def reset(app, *args):
    return app.test_cli_runner().invoke(args=["reset-password", *args])


def test_reset_sets_the_password_clears_lockout_and_keeps_two_step(app, client):
    admin = user_by_role("admin")
    enrol_mfa(admin)
    admin.failed_logins, admin.locked_until = 6, utcnow() + timedelta(minutes=15)
    db.session.commit()

    result = reset(app, "--email", admin.email.upper(), "--reason", REASON, "--password", NEW_PASSWORD)

    assert result.exit_code == 0, result.output
    db.session.refresh(admin)
    assert admin.check_password(NEW_PASSWORD) and not admin.check_password(DEMO_PASSWORD)
    assert admin.failed_logins == 0 and admin.locked_until is None
    assert admin.mfa_enabled and not admin.must_change_password
    r = client.post("/auth/login", data={"email": admin.email, "password": NEW_PASSWORD})
    assert r.status_code == 302 and r.headers["Location"].endswith("/auth/mfa/verify")


def test_reset_is_recorded_in_the_audit_trail_without_the_password(app):
    admin = user_by_role("admin")
    reset(app, "--email", admin.email, "--reason", REASON, "--password", NEW_PASSWORD)

    event = AuditEvent.query.filter_by(event_type="auth.password_reset").one()
    assert event.target_id == admin.id and event.reason == REASON and event.actor_id is None
    assert NEW_PASSWORD not in (event.details or "") and "auth.password_reset" in SENSITIVE_EVENTS


def test_require_change_makes_the_person_choose_their_own_password(app):
    agent = user_by_role("support")
    result = reset(app, "--email", agent.email, "--reason", REASON, "--require-change", "--password", NEW_PASSWORD)
    assert result.exit_code == 0, result.output
    db.session.refresh(agent)
    assert agent.must_change_password


def test_reset_refuses_weak_passwords_short_reasons_and_non_staff(app):
    admin, reporter = user_by_role("admin"), user_by_role("reporter")
    cases = [
        (["--email", admin.email, "--reason", REASON, "--password", "password1234"], "Weak password"),
        (["--email", admin.email, "--reason", "forgot", "--password", NEW_PASSWORD], "at least 10 characters"),
        (["--email", "nobody@example.org", "--reason", REASON, "--password", NEW_PASSWORD], "No staff account"),
        (["--email", reporter.email, "--reason", REASON, "--password", NEW_PASSWORD], "No staff account"),
    ]
    for args, message in cases:
        result = reset(app, *args)
        assert result.exit_code != 0 and message in result.output, (args, result.output)
    assert User.query.get(admin.id).check_password(DEMO_PASSWORD)
    assert AuditEvent.query.filter_by(event_type="auth.password_reset").count() == 0
