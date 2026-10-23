"""Administration & Governance: staff, roles, policy, availability, contacts, health, audit, retention."""

from __future__ import annotations

import csv
import io
from datetime import date

from flask import Response, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import permissions as P
from app.extensions import db
from app.forms import (
    DepartmentConfigForm,
    EmergencyContactForm,
    EmptyForm,
    ReasonForm,
    RoleForm,
    SettingsForm,
    StaffUserForm,
    VerifyContactForm,
    add_error,
    add_errors,
)
from app.i18n import translate as t
from app.models.audit import SENSITIVE_EVENTS, AuditEvent
from app.models.base import utcnow
from app.models.case import Case
from app.models.evidence import Evidence
from app.models.settings import DepartmentConfig, EmergencyContact, SiteSetting
from app.models.user import User
from app.routes.workspace import any_permission, staff_required, workspace_bp
from app.services import audit as audit_svc
from app.services import identity as identity_svc
from app.services.security import password_problems


def _set(key: str, value: str) -> None:
    row = db.session.get(SiteSetting, key)
    if row is None:
        row = SiteSetting(key=key)
        db.session.add(row)
    row.value = value
    row.updated_by_id = current_user.id


def _get(key: str, default: str = "") -> str:
    row = db.session.get(SiteSetting, key)
    return row.value if row else default


@workspace_bp.route("/admin/users", methods=["GET", "POST"])
@staff_required(P.ADMIN_USERS)
def admin_users():
    form = StaffUserForm()
    if form.validate_on_submit():
        email = (form.email.data or "").strip().lower()
        problems = password_problems(form.password.data or "", email=email, name=form.name.data or "")
        if problems:
            add_errors(form.password, problems)
        elif User.query.filter_by(email=email).first():
            add_error(form.email, "validation.email_taken")
        else:
            user = User(
                email=email,
                name=(form.name.data or "").strip(),
                role=form.role.data,
                must_change_password=True,
                created_by_id=current_user.id,
            )
            user.set_password(form.password.data or "")
            db.session.add(user)
            db.session.flush()
            audit_svc.record("admin.user_created", actor=current_user, target_type="user", target_id=user.id, details={"role": user.role})
            db.session.commit()
            flash(t("admin.user_created"), "success")
            return redirect(url_for("workspace.admin_users"))
    users = User.query.order_by(User.role, User.name).all()
    return render_template("workspace/admin/users.html", users=users, form=form, role_form=RoleForm(), reason_form=ReasonForm())


@workspace_bp.route("/admin/users/<int:user_id>/role", methods=["POST"])
@staff_required(P.ADMIN_ROLES)
def admin_user_role(user_id: int):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    form = RoleForm()
    if form.validate_on_submit():
        if user.id == current_user.id and (form.role.data != P.ROLE_ADMIN or not form.active.data):
            flash(t("admin.cannot_change_self"), "error")
            return redirect(url_for("workspace.admin_users"))
        old = (user.role, user.active)
        user.role = form.role.data
        user.active = bool(form.active.data)
        if user.role not in P.PRIVILEGED_ROLES:
            pass
        audit_svc.record(
            "admin.role_changed",
            actor=current_user,
            target_type="user",
            target_id=user.id,
            reason=form.reason.data,
            details={"from": old[0], "to": user.role, "active": user.active},
        )
        db.session.commit()
        flash(t("admin.role_saved"), "success")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(url_for("workspace.admin_users"))


@workspace_bp.route("/admin/users/<int:user_id>/reset-mfa", methods=["POST"])
@staff_required(P.ADMIN_USERS)
def admin_user_reset_mfa(user_id: int):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    form = ReasonForm()
    if form.validate_on_submit():
        user.mfa_enabled = False
        user.mfa_secret_enc = None
        user.mfa_enrolled_at = None
        audit_svc.record("admin.mfa_reset", actor=current_user, target_type="user", target_id=user.id, reason=form.reason.data)
        db.session.commit()
        flash(t("admin.mfa_reset_done"), "success")
    else:
        flash(t("access.reason_required"), "error")
    return redirect(url_for("workspace.admin_users"))


@workspace_bp.route("/admin/departments", methods=["GET"])
@staff_required(P.ADMIN_CONFIG)
def admin_departments():
    configs = {c.department: c for c in DepartmentConfig.query.all()}
    rows = []
    for dept in P.DEPARTMENTS:
        cfg = configs.get(dept)
        if cfg is None:
            cfg = DepartmentConfig(department=dept, is_staffed=False)
            db.session.add(cfg)
        rows.append((dept, cfg, DepartmentConfigForm(obj=cfg, prefix=dept)))
    db.session.commit()
    staff_counts = {
        dept: User.query.filter(User.active.is_(True), User.role.in_([r for r, d in P.ROLE_DEPARTMENT.items() if d == dept])).count()
        for dept in P.DEPARTMENTS
    }
    return render_template("workspace/admin/departments.html", rows=rows, staff_counts=staff_counts)


@workspace_bp.route("/admin/departments/<department>", methods=["POST"])
@staff_required(P.ADMIN_CONFIG)
def admin_department_save(department: str):
    if department not in P.DEPARTMENTS:
        abort(404)
    cfg = DepartmentConfig.query.filter_by(department=department).first() or DepartmentConfig(department=department)
    form = DepartmentConfigForm(prefix=department)
    if form.validate_on_submit():
        staff_in_dept = User.query.filter(
            User.active.is_(True), User.role.in_([r for r, d in P.ROLE_DEPARTMENT.items() if d == department])
        ).count()
        if form.is_staffed.data and staff_in_dept == 0:
            flash(t("admin.cannot_mark_staffed"), "error")
            return redirect(url_for("workspace.admin_departments"))
        cfg.is_staffed = bool(form.is_staffed.data)
        cfg.accepts_cases = bool(form.accepts_cases.data)
        cfg.hours_en, cfg.hours_bn = form.hours_en.data or None, form.hours_bn.data or None
        cfg.notice_en, cfg.notice_bn = form.notice_en.data or None, form.notice_bn.data or None
        cfg.updated_by_id = current_user.id
        db.session.add(cfg)
        audit_svc.record(
            "admin.department_config",
            actor=current_user,
            target_type="department",
            details={"department": department, "staffed": cfg.is_staffed},
        )
        db.session.commit()
        flash(t("admin.saved"), "success")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(url_for("workspace.admin_departments"))


@workspace_bp.route("/admin/contacts", methods=["GET", "POST"])
@staff_required(P.ADMIN_CONFIG)
def admin_contacts():
    form = EmergencyContactForm()
    if form.validate_on_submit():
        contact = EmergencyContact(
            kind=form.kind.data,
            name_en=form.name_en.data,
            name_bn=form.name_bn.data or None,
            number=form.number.data,
            description_en=form.description_en.data or None,
            description_bn=form.description_bn.data or None,
            is_active=bool(form.is_active.data),
            verified=False,
            sort_order=EmergencyContact.query.count(),
        )
        db.session.add(contact)
        audit_svc.record("admin.contact_created", actor=current_user, target_type="contact")
        db.session.commit()
        flash(t("admin.saved"), "success")
        return redirect(url_for("workspace.admin_contacts"))
    contacts = EmergencyContact.query.order_by(EmergencyContact.sort_order).all()
    return render_template(
        "workspace/admin/contacts.html", contacts=contacts, form=form, verify_form=VerifyContactForm(), empty_form=EmptyForm()
    )


@workspace_bp.route("/admin/contacts/<int:contact_id>/verify", methods=["POST"])
@staff_required(P.ADMIN_CONFIG)
def admin_contact_verify(contact_id: int):
    contact = db.session.get(EmergencyContact, contact_id)
    if contact is None:
        abort(404)
    form = VerifyContactForm()
    if form.validate_on_submit():
        contact.verified = True
        contact.verified_by_id = current_user.id
        contact.verified_at = utcnow()
        contact.verification_note = form.verification_note.data
        audit_svc.record(
            "admin.contact_verified", actor=current_user, target_type="contact", target_id=contact.id, reason=form.verification_note.data
        )
        db.session.commit()
        flash(t("admin.contact_verified"), "success")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(url_for("workspace.admin_contacts"))


@workspace_bp.route("/admin/contacts/<int:contact_id>/toggle", methods=["POST"])
@staff_required(P.ADMIN_CONFIG)
def admin_contact_toggle(contact_id: int):
    contact = db.session.get(EmergencyContact, contact_id)
    if contact is None:
        abort(404)
    if EmptyForm().validate_on_submit():
        contact.is_active = not contact.is_active
        if request.form.get("unverify") == "1":
            contact.verified = False
        audit_svc.record(
            "admin.contact_toggled", actor=current_user, target_type="contact", target_id=contact.id, details={"active": contact.is_active}
        )
        db.session.commit()
    return redirect(url_for("workspace.admin_contacts"))


@workspace_bp.route("/admin/settings", methods=["GET", "POST"])
@staff_required(P.ADMIN_CONFIG)
def admin_settings():
    form = SettingsForm()
    if form.validate_on_submit():
        _set("mfa_required", "1" if form.mfa_required.data else "0")
        _set("public_registration", "1" if form.public_registration.data else "0")
        _set("announcement_en", form.announcement_en.data or "")
        _set("announcement_bn", form.announcement_bn.data or "")
        audit_svc.record(
            "admin.settings",
            actor=current_user,
            target_type="settings",
            details={"mfa_required": form.mfa_required.data, "public_registration": form.public_registration.data},
        )
        db.session.commit()
        flash(t("admin.saved"), "success")
        return redirect(url_for("workspace.admin_settings"))
    if request.method == "GET":
        form.mfa_required.data = _get("mfa_required", "1") == "1"
        form.public_registration.data = _get("public_registration", "1") == "1"
        form.announcement_en.data = _get("announcement_en")
        form.announcement_bn.data = _get("announcement_bn")
    return render_template("workspace/admin/settings.html", form=form)


@workspace_bp.route("/admin/health")
@staff_required(P.ADMIN_HEALTH)
def admin_health():
    cfg = current_app.config
    checks = []
    try:
        db.session.execute(db.text("SELECT 1"))
        checks.append(("database", True, cfg["SQLALCHEMY_DATABASE_URI"].split("://", 1)[0]))
    except Exception as exc:  # noqa: BLE001
        checks.append(("database", False, exc.__class__.__name__))
    legacy = Evidence.query.filter(Evidence.data_enc.is_(None)).count()
    checks.append(("evidence_storage", True, "database, encrypted" + (f"; {legacy} older file(s) still on disk" if legacy else "")))
    checks.append(
        ("malware_scanner", bool(cfg.get("CLAMD_SOCKET")), cfg.get("CLAMD_SOCKET") or "not configured — uploads are marked 'not scanned'")
    )
    checks.append(
        (
            "secret_key",
            cfg["SECRET_KEY"] not in ("dev-secret-change-in-prod", "") and len(cfg["SECRET_KEY"]) >= 32,
            "configured" if len(cfg["SECRET_KEY"]) >= 32 else "weak or default",
        )
    )
    checks.append(
        (
            "identity_encryption_key",
            bool(cfg.get("IDENTITY_ENCRYPTION_KEY")),
            "configured" if cfg.get("IDENTITY_ENCRYPTION_KEY") else "derived from SECRET_KEY (development only)",
        )
    )
    checks.append(("rate_limit_storage", cfg.get("RATELIMIT_STORAGE_URI", "memory://") != "memory://", cfg.get("RATELIMIT_STORAGE_URI")))
    checks.append(
        (
            "session_cookie_secure",
            bool(cfg.get("SESSION_COOKIE_SECURE")),
            "on" if cfg.get("SESSION_COOKIE_SECURE") else "off (set in production)",
        )
    )
    checks.append(("outbound_email", bool(cfg.get("MAIL_SERVER")), cfg.get("MAIL_SERVER") or "not configured — no notifications are sent"))
    checks.append(("mfa_required_for_staff", _get("mfa_required", "1") == "1", "on" if _get("mfa_required", "1") == "1" else "OFF"))
    counts = {
        "users": User.query.count(),
        "staff": User.query.filter(User.role.in_(P.STAFF_ROLES)).count(),
        "mfa_enrolled": User.query.filter(User.role.in_(P.STAFF_ROLES), User.mfa_enabled.is_(True)).count(),
        "cases": Case.query.count(),
        "audit_events": AuditEvent.query.count(),
    }
    return render_template("workspace/admin/health.html", checks=checks, counts=counts, env=cfg.get("ENV_NAME"))


@workspace_bp.route("/admin/audit")
@any_permission(P.AUDIT_VIEW_ALL, P.AUDIT_VIEW_DEPT)
def audit():
    q = AuditEvent.query
    if not current_user.can(P.AUDIT_VIEW_ALL):
        dept_roles = [r for r, d in P.ROLE_DEPARTMENT.items() if d == current_user.department]
        q = q.filter(AuditEvent.actor_role.in_(dept_roles))
    if request.args.get("sensitive") == "1":
        q = q.filter(AuditEvent.event_type.in_(SENSITIVE_EVENTS))
    if request.args.get("event"):
        q = q.filter(AuditEvent.event_type == request.args["event"])
    if request.args.get("case"):
        case = Case.query.filter_by(reference=request.args["case"].upper()).first()
        q = q.filter(AuditEvent.case_id == (case.id if case else -1))
    if request.args.get("actor", type=int):
        q = q.filter(AuditEvent.actor_id == request.args.get("actor", type=int))
    page = max(request.args.get("page", 1, type=int), 1)
    pagination = q.order_by(AuditEvent.created_at.desc()).paginate(page=page, per_page=50, error_out=False)
    event_types = [r[0] for r in db.session.query(AuditEvent.event_type).distinct().order_by(AuditEvent.event_type).all()]
    return render_template("workspace/admin/audit.html", pagination=pagination, event_types=event_types, sensitive_events=SENSITIVE_EVENTS)


@workspace_bp.route("/admin/audit/export", methods=["POST"])
@staff_required(P.AUDIT_VIEW_ALL)
def audit_export():
    form = ReasonForm()
    if not form.validate_on_submit():
        flash(t("access.reason_required"), "error")
        return redirect(url_for("workspace.audit"))
    audit_mod_record = audit_svc.record("audit.export", actor=current_user, target_type="audit", reason=form.reason.data, commit=True)
    rows = AuditEvent.query.order_by(AuditEvent.created_at.desc()).limit(5000).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "created_at", "actor_id", "actor_role", "event_type", "target_type", "target_id", "case_id", "reason"])
    for r in rows:
        writer.writerow(
            [
                r.id,
                r.created_at.isoformat(),
                r.actor_id,
                r.actor_role,
                r.event_type,
                r.target_type,
                r.target_id,
                r.case_id,
                (r.reason or "").replace("\n", " "),
            ]
        )
    del audit_mod_record
    return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=audit-export.csv"})


@workspace_bp.route("/admin/permissions")
@staff_required(P.WORKSPACE)
def admin_permissions():
    return render_template(
        "workspace/admin/permissions.html",
        roles=P.STAFF_ROLES,
        matrix=P.ROLE_PERMISSIONS,
        sensitive=P.SENSITIVE_ACTIONS,
        all_perms=sorted(P.ALL_PERMISSIONS),
    )


@workspace_bp.route("/admin/retention", methods=["GET"])
@staff_required(P.ADMIN_CONFIG)
def admin_retention():
    due = (
        Case.query.filter(Case.retention_review_at.isnot(None), Case.retention_review_at <= date.today())
        .order_by(Case.retention_review_at)
        .all()
    )
    upcoming = (
        Case.query.filter(Case.retention_review_at.isnot(None), Case.retention_review_at > date.today())
        .order_by(Case.retention_review_at)
        .limit(50)
        .all()
    )
    return render_template(
        "workspace/admin/retention.html",
        due=due,
        upcoming=upcoming,
        form=ReasonForm(),
        days=current_app.config.get("DATA_RETENTION_DAYS_CLOSED_CASES"),
    )


@workspace_bp.route("/admin/retention/<reference>/purge-identity", methods=["POST"])
@staff_required(P.ADMIN_CONFIG)
def admin_purge_identity(reference: str):
    case = Case.query.filter_by(reference=reference.upper()).first_or_404()
    form = ReasonForm()
    if form.validate_on_submit() and not case.is_open:
        identity_svc.purge(case, current_user, form.reason.data or "")
        flash(t("admin.identity_purged"), "success")
    else:
        flash(t("access.reason_required"), "error")
    return redirect(url_for("workspace.admin_retention"))
