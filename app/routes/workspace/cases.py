"""Case workspace: queue, detail, triage, severity, lifecycle, notes, identity unlock, evidence."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from cryptography.fernet import InvalidToken
from flask import abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user

from app import permissions as P
from app.extensions import db
from app.forms import (
    AssignForm,
    CustodyForm,
    EvidenceUploadForm,
    FlagForm,
    LegalIntakeForm,
    NoteForm,
    OutcomeForm,
    ReasonForm,
    ReferralForm,
    ReferralUpdateForm,
    ReporterUpdateForm,
    RouteForm,
    SeverityForm,
    ShortReasonForm,
    StatusForm,
)
from app.i18n import translate as t
from app.models.case import OPEN_STATUSES, STATUSES, TRANSITIONS, Case, CaseOutcome, Referral
from app.models.evidence import CustodyRecord, Evidence
from app.models.legal import LegalIntake
from app.models.moderation import ModerationFlag
from app.models.user import User
from app.routes.workspace import staff_required, workspace_bp
from app.services import access, audit, uploads
from app.services import cases as svc
from app.services import identity as identity_svc
from app.services.cases import CaseError


def _case(reference: str) -> Case:
    case = Case.query.filter_by(reference=reference.upper()).first()
    if case is None:
        abort(404)
    return case


def _detail_url(case: Case) -> str:
    return url_for("workspace.case_detail", reference=case.reference)


@workspace_bp.route("/cases")
@staff_required(P.WORKSPACE)
def cases():
    q = access.queue_query(current_user)
    status = request.args.get("status")
    if status in STATUSES:
        q = q.filter(Case.status == status)
    elif request.args.get("scope") != "all":
        q = q.filter(Case.status.in_(OPEN_STATUSES))
    if request.args.get("severity") in ("1", "2", "3", "4"):
        q = q.filter(Case.severity_level == int(request.args["severity"]))
    if request.args.get("safety") == "1":
        q = q.filter(Case.safety_flag.is_(True))
    if request.args.get("mine") == "1":
        from app.models.case import CaseAssignment

        q = q.filter(
            Case.id.in_(CaseAssignment.query.with_entities(CaseAssignment.case_id).filter_by(user_id=current_user.id, active=True))
        )
    if request.args.get("department") in P.DEPARTMENTS and current_user.can(P.CASE_VIEW_METADATA_ANY):
        q = q.filter(Case.department == request.args["department"])
    page = max(request.args.get("page", 1, type=int), 1)
    pagination = q.order_by(Case.safety_flag.desc(), Case.severity_level.desc().nullslast(), Case.created_at.desc()).paginate(
        page=page, per_page=25, error_out=False
    )
    return render_template("workspace/cases/list.html", pagination=pagination, statuses=STATUSES)


@workspace_bp.route("/cases/<reference>")
@staff_required(P.WORKSPACE)
def case_detail(reference: str):
    case = _case(reference)
    access.require_metadata(current_user, case)
    narrative_ok = access.can_view_narrative(current_user, case)
    forms: dict[str, Any] = {}
    if narrative_ok:
        forms = {
            "severity": SeverityForm(),
            "status": StatusForm(),
            "route": RouteForm(),
            "assign": AssignForm(),
            "note": NoteForm(),
            "reporter_update": ReporterUpdateForm(),
            "reason": ReasonForm(),
            "short_reason": ShortReasonForm(),
            "referral": ReferralForm(),
            "referral_update": ReferralUpdateForm(),
            "outcome": OutcomeForm(),
            "evidence": EvidenceUploadForm(),
            "custody": CustodyForm(),
            "legal": LegalIntakeForm(),
            "flag": FlagForm(),
        }
        forms["status"].to_status.choices = [(s, f"status.{s}") for s in TRANSITIONS.get(case.status, ())]
        staff = (
            User.query.filter(User.role.in_(P.STAFF_ROLES), User.active.is_(True), User.role != P.ROLE_ADMIN)
            .order_by(User.role, User.name)
            .all()
        )
        forms["assign"].user_id.choices = [(u.id, f"{u.name} · {t('role.' + u.role)}") for u in staff]
        if case.legal_intake:
            forms["legal"] = LegalIntakeForm(obj=case.legal_intake)
        forms["flag"].target_type.data = "case"
        forms["flag"].target_id.data = case.id
    notes = [n for n in case.notes if access.can_see_note(current_user, n)] if narrative_ok else []
    evidence = [e for e in case.evidence if e.deleted_at is None] if (narrative_ok and current_user.can(P.CASE_EVIDENCE_VIEW)) else []
    return render_template(
        "workspace/cases/detail.html",
        case=case,
        narrative_ok=narrative_ok,
        forms=forms,
        notes=notes,
        evidence=evidence,
        break_glass_form=ReasonForm() if current_user.can(P.CASE_BREAK_GLASS) else None,
    )


def _act(case: Case, perm: str) -> None:
    if not current_user.can(perm) or not access.can_act_on_case(current_user, case):
        abort(403)


@workspace_bp.route("/cases/<reference>/severity", methods=["POST"])
@staff_required(P.CASE_SEVERITY)
def case_severity(reference: str):
    case = _case(reference)
    _act(case, P.CASE_SEVERITY)
    form = SeverityForm()
    if form.validate_on_submit():
        try:
            svc.assess_severity(
                case, current_user, int(form.level.data), form.reasoning.data or "", is_override=bool(form.is_override.data)
            )
            flash(t("severity.saved"), "success")
        except CaseError as exc:
            flash(t(str(exc)), "error")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(_detail_url(case))


@workspace_bp.route("/cases/<reference>/status", methods=["POST"])
@staff_required(P.CASE_STATUS)
def case_status(reference: str):
    case = _case(reference)
    _act(case, P.CASE_STATUS)
    form = StatusForm()
    form.to_status.choices = [(s, s) for s in STATUSES]
    if form.validate_on_submit():
        if form.to_status.data in ("reopened",) and not current_user.can(P.CASE_REOPEN):
            abort(403)
        try:
            svc.change_status(case, current_user, form.to_status.data, form.reason.data or "")
            flash(t("case.status_saved"), "success")
        except CaseError as exc:
            flash(t(str(exc)), "error")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(_detail_url(case))


@workspace_bp.route("/cases/<reference>/route", methods=["POST"])
@staff_required(P.CASE_TRIAGE)
def case_route(reference: str):
    case = _case(reference)
    _act(case, P.CASE_TRIAGE)
    form = RouteForm()
    if form.validate_on_submit():
        try:
            svc.route_case(case, current_user, form.department.data, form.reason.data or "")
            flash(t("case.routed"), "success")
        except CaseError as exc:
            flash(t(str(exc)), "error")
    return redirect(_detail_url(case))


@workspace_bp.route("/cases/<reference>/assign", methods=["POST"])
@staff_required(P.CASE_ASSIGN)
def case_assign(reference: str):
    case = _case(reference)
    if not (access.can_act_on_case(current_user, case) or current_user.can(P.CASE_VIEW_METADATA_ANY)):
        abort(403)
    form = AssignForm()
    form.user_id.choices = [(u.id, u.name) for u in User.query.filter(User.role.in_(P.STAFF_ROLES)).all()]
    if form.validate_on_submit():
        assignee = db.session.get(User, form.user_id.data)
        if assignee is None:
            abort(404)
        try:
            svc.assign(case, current_user, assignee, form.role_in_case.data or "lead")
            flash(t("case.assigned"), "success")
        except CaseError as exc:
            flash(t(str(exc)), "error")
    return redirect(_detail_url(case))


@workspace_bp.route("/cases/<reference>/unassign/<int:user_id>", methods=["POST"])
@staff_required(P.CASE_ASSIGN)
def case_unassign(reference: str, user_id: int):
    case = _case(reference)
    if not (access.can_act_on_case(current_user, case) or current_user.can(P.CASE_VIEW_METADATA_ANY)):
        abort(403)
    svc.unassign(case, current_user, user_id)
    flash(t("case.unassigned"), "success")
    return redirect(_detail_url(case))


@workspace_bp.route("/cases/<reference>/note", methods=["POST"])
@staff_required(P.CASE_NOTE)
def case_note(reference: str):
    case = _case(reference)
    _act(case, P.CASE_NOTE)
    form = NoteForm()
    if form.validate_on_submit():
        svc.add_note(case, current_user, form.body.data or "", visibility=form.visibility.data or "case_team")
        flash(t("case.note_saved"), "success")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(_detail_url(case))


@workspace_bp.route("/cases/<reference>/update", methods=["POST"])
@staff_required(P.CASE_MESSAGE_REPORTER)
def case_update(reference: str):
    case = _case(reference)
    _act(case, P.CASE_MESSAGE_REPORTER)
    form = ReporterUpdateForm()
    if form.validate_on_submit():
        from app.services.redaction import scan_for_identifiers

        if scan_for_identifiers(form.body.data or ""):
            flash(t("case.update_has_identifiers"), "error")
        else:
            svc.add_reporter_update(case, current_user, form.body.data or "")
            flash(t("case.update_saved"), "success")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(_detail_url(case))


@workspace_bp.route("/cases/<reference>/referral", methods=["POST"])
@staff_required(P.CASE_REFERRAL)
def case_referral(reference: str):
    case = _case(reference)
    _act(case, P.CASE_REFERRAL)
    form = ReferralForm()
    if form.validate_on_submit():
        try:
            svc.add_referral(case, current_user, form.data)
            flash(t("referral.saved"), "success")
        except CaseError as exc:
            flash(t(str(exc)), "error")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(_detail_url(case))


@workspace_bp.route("/cases/<reference>/referral/<int:referral_id>", methods=["POST"])
@staff_required(P.CASE_REFERRAL)
def case_referral_update(reference: str, referral_id: int):
    case = _case(reference)
    _act(case, P.CASE_REFERRAL)
    referral = db.session.get(Referral, referral_id)
    if referral is None or referral.case_id != case.id:
        abort(404)
    form = ReferralUpdateForm()
    if form.validate_on_submit():
        try:
            svc.update_referral(referral, current_user, form.status.data, form.confirmation_reference.data, form.notes.data)
            flash(t("referral.updated"), "success")
        except CaseError as exc:
            flash(t(str(exc)), "error")
    return redirect(_detail_url(case))


@workspace_bp.route("/cases/<reference>/outcome", methods=["POST"])
@staff_required(P.CASE_OUTCOME)
def case_outcome(reference: str):
    case = _case(reference)
    _act(case, P.CASE_OUTCOME)
    form = OutcomeForm()
    if form.validate_on_submit():
        try:
            svc.record_outcome(case, current_user, form.data)
            flash(t("outcome.saved"), "success")
        except CaseError as exc:
            flash(t(str(exc)), "error")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(_detail_url(case))


@workspace_bp.route("/cases/<reference>/outcome/<int:outcome_id>/verify", methods=["POST"])
@staff_required(P.CASE_OUTCOME)
def case_outcome_verify(reference: str, outcome_id: int):
    case = _case(reference)
    _act(case, P.CASE_OUTCOME)
    outcome = db.session.get(CaseOutcome, outcome_id)
    if outcome is None or outcome.case_id != case.id:
        abort(404)
    try:
        svc.verify_outcome(outcome, current_user)
        flash(t("outcome.verified"), "success")
    except CaseError as exc:
        flash(t(str(exc)), "error")
    return redirect(_detail_url(case))


@workspace_bp.route("/cases/<reference>/identity", methods=["POST"])
@staff_required(P.WORKSPACE)
def case_identity(reference: str):
    case = _case(reference)
    if not access.can_view_metadata(current_user, case):
        audit.record(
            "identity.unlock_refused",
            actor=current_user,
            target_type="case",
            target_id=case.id,
            case_id=case.id,
            details={"visible": False},
            commit=True,
        )
        abort(403)
    form = ReasonForm()
    if not form.validate_on_submit():
        flash(t("access.reason_required"), "error")
        return redirect(_detail_url(case))
    break_glass = current_user.can(P.CASE_BREAK_GLASS) and not current_user.can(P.CASE_IDENTITY_UNLOCK)
    try:
        payload = identity_svc.unlock(case, current_user, form.reason.data or "", break_glass=break_glass)
    except identity_svc.IdentityAccessDenied:
        abort(403)
    return render_template("workspace/cases/identity.html", case=case, identity=payload, break_glass=break_glass, reason=form.reason.data)


@workspace_bp.route("/cases/<reference>/break-glass", methods=["POST"])
@staff_required(P.CASE_BREAK_GLASS)
def case_break_glass(reference: str):
    case = _case(reference)
    form = ReasonForm()
    if not form.validate_on_submit():
        flash(t("access.reason_required"), "error")
        return redirect(_detail_url(case))
    audit.record(
        "case.break_glass", actor=current_user, target_type="case", target_id=case.id, case_id=case.id, reason=form.reason.data, commit=True
    )
    notes = [n for n in case.notes if n.visibility != "legal_privileged"]
    return render_template("workspace/cases/break_glass.html", case=case, notes=notes, reason=form.reason.data)


@workspace_bp.route("/cases/<reference>/evidence", methods=["POST"])
@staff_required(P.CASE_EVIDENCE_VIEW)
def case_evidence_upload(reference: str):
    case = _case(reference)
    _act(case, P.CASE_EVIDENCE_VIEW)
    form = EvidenceUploadForm()
    if form.validate_on_submit():
        try:
            uploads.store_evidence(case, form.file.data, description=form.description.data, uploaded_by=current_user)
            db.session.commit()
            flash(t("evidence.saved"), "success")
        except uploads.UploadError as exc:
            db.session.rollback()
            flash(t(str(exc)), "error")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(_detail_url(case))


def _evidence(case: Case, evidence_id: int) -> Evidence:
    ev = db.session.get(Evidence, evidence_id)
    if ev is None or ev.case_id != case.id:
        abort(404)
    return ev


@workspace_bp.route("/cases/<reference>/evidence/<int:evidence_id>/download", methods=["POST"])
@staff_required(P.CASE_EVIDENCE_DOWNLOAD)
def case_evidence_download(reference: str, evidence_id: int):
    case = _case(reference)
    ev = _evidence(case, evidence_id)
    form = ShortReasonForm()
    if not form.validate_on_submit():
        flash(t("access.reason_required"), "error")
        return redirect(_detail_url(case))
    export = request.form.get("export") == "1"
    if export and not current_user.can(P.CASE_EVIDENCE_EXPORT):
        abort(403)
    try:
        data = uploads.authorize_download(ev, current_user, form.reason.data or "", export=export)
    except PermissionError:
        abort(403)
    except (FileNotFoundError, InvalidToken):
        abort(404)
    return send_file(BytesIO(data), as_attachment=True, download_name=ev.original_name, mimetype=ev.mime_type, max_age=0)


@workspace_bp.route("/cases/<reference>/evidence/<int:evidence_id>/verify", methods=["POST"])
@staff_required(P.CYBER_CUSTODY)
def case_evidence_verify(reference: str, evidence_id: int):
    case = _case(reference)
    _act(case, P.CYBER_CUSTODY)
    ev = _evidence(case, evidence_id)
    ok = uploads.verify_hash(ev, current_user)
    flash(t("custody.hash_ok") if ok else t("custody.hash_mismatch"), "success" if ok else "error")
    return redirect(_detail_url(case))


@workspace_bp.route("/cases/<reference>/evidence/<int:evidence_id>/custody", methods=["POST"])
@staff_required(P.CYBER_CUSTODY)
def case_evidence_custody(reference: str, evidence_id: int):
    case = _case(reference)
    _act(case, P.CYBER_CUSTODY)
    ev = _evidence(case, evidence_id)
    form = CustodyForm()
    if form.validate_on_submit():
        db.session.add(
            CustodyRecord(
                evidence_id=ev.id, actor_id=current_user.id, action=form.action.data, notes=form.notes.data, hash_at_time=ev.sha256
            )
        )
        audit.record(
            "evidence.custody",
            actor=current_user,
            target_type="evidence",
            target_id=ev.id,
            case_id=case.id,
            details={"action": form.action.data},
        )
        db.session.commit()
        flash(t("custody.saved"), "success")
    return redirect(_detail_url(case))


@workspace_bp.route("/cases/<reference>/legal-intake", methods=["POST"])
@staff_required(P.LEGAL_INTAKE)
def case_legal_intake(reference: str):
    case = _case(reference)
    _act(case, P.LEGAL_INTAKE)
    form = LegalIntakeForm()
    if form.validate_on_submit():
        intake = case.legal_intake or LegalIntake(case_id=case.id, opened_by_id=current_user.id, matter_type="")
        intake.matter_type = form.matter_type.data or ""
        intake.status = form.status.data or "intake"
        intake.deadline = form.deadline.data
        intake.deadline_note = form.deadline_note.data or None
        intake.referral_partner = form.referral_partner.data or None
        intake.qualified_reviewer = form.qualified_reviewer.data or None
        db.session.add(intake)
        audit.record(
            "legal.intake", actor=current_user, target_type="case", target_id=case.id, case_id=case.id, details={"status": intake.status}
        )
        db.session.commit()
        flash(t("legal.saved"), "success")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(_detail_url(case))


@workspace_bp.route("/cases/<reference>/flag", methods=["POST"])
@staff_required(P.MOD_FLAG)
def case_flag(reference: str):
    case = _case(reference)
    access.require_metadata(current_user, case)
    form = FlagForm()
    if form.validate_on_submit():
        flag = ModerationFlag(
            target_type="case", target_id=case.id, reason=form.reason.data, notes=form.notes.data or "", raised_by_id=current_user.id
        )
        db.session.add(flag)
        db.session.flush()
        audit.record(
            "moderation.flagged",
            actor=current_user,
            target_type="case",
            target_id=case.id,
            case_id=case.id,
            details={"reason": flag.reason},
        )
        db.session.commit()
        flash(t("moderation.flag_saved"), "success")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(_detail_url(case))
