"""Authentication: password + TOTP MFA for staff, lockout, anti-enumeration, safe redirects."""

from __future__ import annotations

import base64
import io

import segno
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import bcrypt, db, limiter
from app.forms import ChangePasswordForm, LoginForm, MfaSetupForm, MfaVerifyForm, RegisterForm, add_error, add_errors
from app.i18n import translate as t
from app.models.base import utcnow
from app.models.settings import SiteSetting
from app.models.user import User
from app.services import audit
from app.services.security import (
    load_mfa_secret,
    mfa_required_for,
    new_mfa_secret,
    password_problems,
    provisioning_uri,
    reset_session_keep_locale,
    safe_next,
    store_mfa_secret,
    verify_totp,
)

auth_bp = Blueprint("auth", __name__)

# Used to equalise timing when the email is unknown.
_DUMMY_HASH = "$2b$12$C6UzMDM.H6dfI/f/IKcEeO5zF9f4fQ2u0t2mYbZ0C1l4lX0wNEuxa"


def _home_for(user) -> str:
    return url_for("workspace.home") if user.is_staff else url_for("public.my_reports")


def _complete_login(user: User) -> None:
    user.register_successful_login()
    session.permanent = True
    login_user(user)
    session.pop("pre_mfa_user_id", None)
    session.pop("pre_mfa_next", None)
    session.pop("mfa_attempts", None)
    audit.record("auth.login", actor=user, target_type="user", target_id=user.id)
    db.session.commit()


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute; 60 per hour", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))
    form = LoginForm()
    if request.method == "GET":
        form.next.data = request.args.get("next", "")
    if form.validate_on_submit():
        email = (form.email.data or "").strip().lower()
        password = form.password.data or ""
        user = User.query.filter_by(email=email).first()
        ok = False
        if user is None:
            bcrypt.check_password_hash(_DUMMY_HASH, password)
        elif user.is_locked():
            audit.record("auth.login_locked", target_type="user", target_id=user.id, commit=True)
        else:
            ok = user.check_password(password)
        if not ok or user is None or not user.active:
            if user is not None and not user.is_locked():
                from flask import current_app

                user.register_failed_login(current_app.config["LOGIN_MAX_FAILURES"], current_app.config["LOGIN_LOCKOUT_MINUTES"])
            audit.record("auth.login_failed", target_type="user", target_id=getattr(user, "id", None), commit=True)
            flash(t("auth.invalid"), "error")
            return render_template("auth/login.html", form=form), 200
        reset_session_keep_locale()
        nxt = safe_next(_home_for(user))
        if mfa_required_for(user):
            session["pre_mfa_user_id"] = user.id
            session["pre_mfa_next"] = nxt
            session["pre_mfa_at"] = utcnow().isoformat()
            if not user.mfa_enabled:
                flash(t("auth.mfa_enrol_required"), "info")
                return redirect(url_for("auth.mfa_setup"))
            return redirect(url_for("auth.mfa_verify"))
        _complete_login(user)
        return redirect(nxt)
    return render_template("auth/login.html", form=form)


def _pre_mfa_user() -> User:
    uid = session.get("pre_mfa_user_id")
    if not uid:
        abort(403)
    user = db.session.get(User, uid)
    if user is None or not user.active:
        abort(403)
    return user


def _qr_data_uri(uri: str) -> str:
    buf = io.BytesIO()
    segno.make(uri, error="m").save(buf, kind="svg", scale=4, border=1, dark="#1f2326", light=None)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


@auth_bp.route("/mfa/setup", methods=["GET", "POST"])
@limiter.limit("20 per hour", methods=["POST"])
def mfa_setup():
    if current_user.is_authenticated:
        user = current_user
        if user.mfa_enabled:
            flash(t("auth.mfa_already"), "info")
            return redirect(_home_for(user))
    else:
        user = _pre_mfa_user()
    secret = session.get("mfa_setup_secret")
    if not secret:
        secret = new_mfa_secret()
        session["mfa_setup_secret"] = secret
    form = MfaSetupForm()
    if form.validate_on_submit():
        if verify_totp(secret, form.code.data or ""):
            store_mfa_secret(user, secret)
            user.mfa_enabled = True
            user.mfa_enrolled_at = utcnow()
            session.pop("mfa_setup_secret", None)
            audit.record("auth.mfa_enrolled", actor=user, target_type="user", target_id=user.id)
            db.session.commit()
            flash(t("auth.mfa_enrolled"), "success")
            if current_user.is_authenticated:
                return redirect(_home_for(user))
            nxt = session.get("pre_mfa_next") or _home_for(user)
            _complete_login(user)
            return redirect(nxt)
        flash(t("auth.mfa_wrong"), "error")
    uri = provisioning_uri(user, secret)
    return render_template("auth/mfa_setup.html", form=form, qr=_qr_data_uri(uri), secret=secret, email=user.email)


@auth_bp.route("/mfa/verify", methods=["GET", "POST"])
@limiter.limit("10 per minute; 30 per hour", methods=["POST"])
def mfa_verify():
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))
    user = _pre_mfa_user()
    if not user.mfa_enabled:
        return redirect(url_for("auth.mfa_setup"))
    form = MfaVerifyForm()
    if form.validate_on_submit():
        attempts = session.get("mfa_attempts", 0) + 1
        session["mfa_attempts"] = attempts
        secret = load_mfa_secret(user)
        if secret and verify_totp(secret, form.code.data or ""):
            nxt = session.get("pre_mfa_next") or _home_for(user)
            _complete_login(user)
            return redirect(nxt)
        audit.record("auth.mfa_failed", target_type="user", target_id=user.id, commit=True)
        if attempts >= 5:
            session.clear()
            flash(t("auth.mfa_too_many"), "error")
            return redirect(url_for("auth.login"))
        flash(t("auth.mfa_wrong"), "error")
    return render_template("auth/mfa_verify.html", form=form)


@auth_bp.route("/logout", methods=["POST", "GET"])
def logout():
    if current_user.is_authenticated:
        audit.record("auth.logout", actor=current_user, target_type="user", target_id=current_user.id, commit=True)
        logout_user()
    session.clear()
    return redirect(url_for("public.home"))


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def register():
    setting = db.session.get(SiteSetting, "public_registration")
    if setting is not None and setting.value == "0":
        abort(404)
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))
    form = RegisterForm()
    if form.validate_on_submit():
        email = (form.email.data or "").strip().lower()
        if form.password.data != form.password2.data:
            add_error(form.password2, "validation.password_match")
            return render_template("auth/register.html", form=form)
        problems = password_problems(form.password.data or "", email=email, name=form.name.data or "")
        if problems:
            add_errors(form.password, problems)
            return render_template("auth/register.html", form=form)
        if User.query.filter_by(email=email).first() is None:
            user = User(email=email, name=(form.name.data or "").strip(), role="reporter")
            user.set_password(form.password.data or "")
            db.session.add(user)
            db.session.flush()
            audit.record("auth.registered", actor=user, target_type="user", target_id=user.id)
            db.session.commit()
        else:
            audit.record("auth.register_duplicate", commit=True)
        # Same message whether or not the email existed (no account enumeration).
        flash(t("auth.registered"), "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/register.html", form=form)


@auth_bp.route("/password", methods=["GET", "POST"])
@login_required
@limiter.limit("10 per hour", methods=["POST"])
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current.data or ""):
            flash(t("auth.invalid_current"), "error")
            return render_template("auth/password.html", form=form)
        if form.password.data != form.password2.data:
            add_error(form.password2, "validation.password_match")
            return render_template("auth/password.html", form=form)
        problems = password_problems(form.password.data or "", email=current_user.email, name=current_user.name)
        if problems:
            add_errors(form.password, problems)
            return render_template("auth/password.html", form=form)
        current_user.set_password(form.password.data or "")
        current_user.must_change_password = False
        audit.record("auth.password_changed", actor=current_user, target_type="user", target_id=current_user.id)
        db.session.commit()
        flash(t("auth.password_changed"), "success")
        return redirect(_home_for(current_user))
    return render_template("auth/password.html", form=form)
