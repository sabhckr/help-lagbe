"""Moderation: flags, actions, appeals, and public requests (corrections, appeals, removals, complaints)."""

from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import permissions as P
from app.crypto import decrypt_json
from app.extensions import db
from app.forms import AppealDecisionForm, FlagForm, ModerationActionForm, RequestDecisionForm
from app.i18n import translate as t
from app.models.base import utcnow
from app.models.case import Case
from app.models.moderation import ModerationAppeal, ModerationFlag
from app.models.publication import PublicRequest
from app.routes.workspace import any_permission, staff_required, workspace_bp
from app.services import audit


@workspace_bp.route("/moderation")
@staff_required(P.MOD_QUEUE)
def moderation():
    status = request.args.get("status", "open")
    flags = (
        ModerationFlag.query.filter_by(status=status).order_by(ModerationFlag.created_at.desc()).limit(200).all()
        if status in ("open", "actioned", "dismissed")
        else []
    )
    appeals = ModerationAppeal.query.filter_by(status="open").order_by(ModerationAppeal.created_at).all()
    return render_template(
        "workspace/moderation/queue.html",
        flags=flags,
        appeals=appeals,
        status=status,
        action_form=ModerationActionForm(),
        appeal_form=AppealDecisionForm(),
    )


@workspace_bp.route("/moderation/flags/new", methods=["GET", "POST"])
@staff_required(P.MOD_FLAG)
def flag_new():
    form = FlagForm()
    if form.validate_on_submit():
        flag = ModerationFlag(
            target_type=form.target_type.data,
            target_id=form.target_id.data,
            reason=form.reason.data,
            notes=form.notes.data or "",
            raised_by_id=current_user.id,
        )
        db.session.add(flag)
        db.session.flush()
        audit.record(
            "moderation.flagged",
            actor=current_user,
            target_type=flag.target_type,
            target_id=flag.target_id,
            details={"reason": flag.reason},
        )
        db.session.commit()
        flash(t("moderation.flag_saved"), "success")
        return redirect(url_for("workspace.home"))
    return render_template("workspace/moderation/flag_new.html", form=form)


@workspace_bp.route("/moderation/flags/<int:flag_id>", methods=["POST"])
@staff_required(P.MOD_ACT)
def flag_act(flag_id: int):
    flag = db.session.get(ModerationFlag, flag_id)
    if flag is None:
        abort(404)
    form = ModerationActionForm()
    if form.validate_on_submit():
        flag.status = form.decision.data
        flag.action_taken = form.action_taken.data
        flag.handled_by_id = current_user.id
        flag.handled_at = utcnow()
        if flag.target_type == "case":
            case = db.session.get(Case, flag.target_id)
            if case is not None:
                if form.hold_case.data:
                    case.moderation_hold = True
                if form.mark_spam.data:
                    case.is_spam = True
        audit.record(
            "moderation.actioned",
            actor=current_user,
            target_type=flag.target_type,
            target_id=flag.target_id,
            details={"decision": flag.status},
        )
        db.session.commit()
        flash(t("moderation.saved"), "success")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(url_for("workspace.moderation"))


@workspace_bp.route("/moderation/appeals/<int:appeal_id>", methods=["POST"])
@staff_required(P.MOD_APPEALS)
def appeal_decide(appeal_id: int):
    appeal = db.session.get(ModerationAppeal, appeal_id)
    if appeal is None:
        abort(404)
    if appeal.flag.handled_by_id == current_user.id:
        flash(t("moderation.error_same_moderator"), "error")
        return redirect(url_for("workspace.moderation"))
    form = AppealDecisionForm()
    if form.validate_on_submit():
        appeal.status = form.decision.data
        appeal.decision = form.notes.data
        appeal.decided_by_id = current_user.id
        appeal.decided_at = utcnow()
        if form.decision.data == "upheld" and appeal.flag.target_type == "case":
            case = db.session.get(Case, appeal.flag.target_id)
            if case is not None:
                case.moderation_hold = False
                case.is_spam = False
        audit.record(
            "moderation.appeal_decided", actor=current_user, target_type="appeal", target_id=appeal.id, details={"decision": appeal.status}
        )
        db.session.commit()
        flash(t("moderation.saved"), "success")
    return redirect(url_for("workspace.moderation"))


@workspace_bp.route("/requests")
@any_permission(P.MOD_QUEUE, P.PUB_CORRECT, P.CASE_APPEAL_HANDLE)
def requests_queue():
    status = request.args.get("status", "open")
    q = PublicRequest.query
    if status in ("open", "in_review", "upheld", "rejected", "closed"):
        q = q.filter_by(status=status)
    if not current_user.can(P.MOD_QUEUE):
        allowed = []
        if current_user.can(P.PUB_CORRECT):
            allowed += ["correction", "right_of_reply", "removal"]
        if current_user.can(P.CASE_APPEAL_HANDLE):
            allowed += ["appeal", "complaint"]
        q = q.filter(PublicRequest.request_type.in_(allowed))
    items = q.order_by(PublicRequest.created_at.desc()).limit(200).all()
    return render_template("workspace/moderation/requests.html", items=items, status=status, form=RequestDecisionForm())


@workspace_bp.route("/requests/<int:request_id>", methods=["GET", "POST"])
@any_permission(P.MOD_QUEUE, P.PUB_CORRECT, P.CASE_APPEAL_HANDLE)
def request_detail(request_id: int):
    item = db.session.get(PublicRequest, request_id)
    if item is None:
        abort(404)
    form = RequestDecisionForm()
    if form.validate_on_submit():
        item.status = form.status.data
        item.resolution = form.resolution.data
        item.handled_by_id = current_user.id
        audit.record(
            "request.decided",
            actor=current_user,
            target_type="public_request",
            target_id=item.id,
            details={"status": item.status, "type": item.request_type},
        )
        db.session.commit()
        flash(t("request.saved"), "success")
        return redirect(url_for("workspace.requests_queue"))
    contact = None
    if item.contact_enc and request.args.get("reveal") == "1":
        contact = decrypt_json(item.contact_enc).get("contact")
        audit.record("request.contact_revealed", actor=current_user, target_type="public_request", target_id=item.id, commit=True)
    return render_template("workspace/moderation/request_detail.html", item=item, form=form, contact=contact)
