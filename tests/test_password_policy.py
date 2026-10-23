"""Password policy: guessable passwords are refused everywhere a password is set."""

import pytest

from app.services.security import password_problems


@pytest.mark.parametrize(
    "weak",
    [
        "password1234",
        "Password2026!",
        "MyPassword2026",
        "dhaka12345678",
        "Bangladesh2026",
        "2026helplagbe",
        "welcome12345",
        "123456789012",
        "000000000000",
        "abcdefghijkl",
        "qwertyuiopas",
        "abababababab",
        "!!!!@@@@####",
    ],
)
def test_guessable_passwords_are_refused(app, weak):
    assert "validation.password_common" in password_problems(weak)


@pytest.mark.parametrize(
    "strong",
    [
        "correct horse battery staple",
        "Local-only rehearsal 2026!",
        "tin-roof-mango-river-41",
        "ঢাকা শহরে বৃষ্টি নামল আজ",
    ],
)
def test_long_unpredictable_passwords_pass(app, strong):
    assert password_problems(strong) == []


def test_create_staff_refuses_a_guessable_password(app):
    result = app.test_cli_runner().invoke(
        args=["create-staff", "--email", "new.admin@example.org", "--name", "New Admin", "--role", "admin", "--password", "password1234"]
    )
    assert result.exit_code != 0 and "Weak password" in result.output
