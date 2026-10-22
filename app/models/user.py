from __future__ import annotations

from datetime import datetime, timedelta

from flask_login import UserMixin
from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app import permissions as P
from app.extensions import Model, bcrypt
from app.models.base import utcnow


class User(UserMixin, Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(190), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default=P.ROLE_REPORTER, index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    mfa_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mfa_enrolled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    failed_logins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    preferred_lang: Mapped[str | None] = mapped_column(String(5), nullable=True)
    session_token: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    created_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ---- authentication -------------------------------------------------------------------
    def set_password(self, password: str) -> None:
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")
        self.password_changed_at = utcnow()

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return bcrypt.check_password_hash(self.password_hash, password)

    @property
    def is_active(self) -> bool:  # Flask-Login
        return bool(self.active)

    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > utcnow())

    def register_failed_login(self, max_failures: int, lockout_minutes: int) -> None:
        self.failed_logins = (self.failed_logins or 0) + 1
        if self.failed_logins >= max_failures:
            self.locked_until = utcnow() + timedelta(minutes=lockout_minutes)
            self.failed_logins = 0

    def register_successful_login(self) -> None:
        self.failed_logins = 0
        self.locked_until = None
        self.last_login_at = utcnow()

    # ---- authorisation ---------------------------------------------------------------------
    @property
    def is_staff(self) -> bool:
        return self.role in P.STAFF_ROLES

    @property
    def is_privileged(self) -> bool:
        return self.role in P.PRIVILEGED_ROLES

    @property
    def department(self) -> str | None:
        return P.department_for_role(self.role)

    @property
    def permissions(self) -> frozenset[str]:
        return P.permissions_for(self.role)

    def can(self, *perms: str) -> bool:
        return self.active and P.role_has(self.role, *perms)

    def can_any(self, *perms: str) -> bool:
        return self.active and P.role_has_any(self.role, perms)

    def __repr__(self) -> str:  # never include email in repr (logs)
        return f"<User id={self.id} role={self.role}>"
