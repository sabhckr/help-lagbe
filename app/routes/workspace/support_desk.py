"""Human Support & Safeguarding: agent presence, queue, private conversations, escalation, follow-up."""

from __future__ import annotations

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from app import permissions as P
from app.extensions import db
from app.forms import EmptyForm, EscalateForm, FollowUpForm, ReasonForm, SupportMessageForm
from app.i18n import translate as t
from app.models.case import Case
from app.models.support import CONV_CLOSED, AgentPresence, SupportConversation
from app.routes.workspace import any_permission, staff_required, workspace_bp
from app.services import access
from app.services import support as svc


def _conv(reference: str) -> SupportConversation:
    conv = SupportConversation.query.filter_by(reference=reference.upper()).first()
    if conv is None:
        abort(404)
    return conv


@workspace_bp.route("/support")
@any_permission(P.SUPPORT_QUEUE, P.SUPPORT_SUPERVISE)
def support_queue():
    presence = AgentPresence.query.filter_by(user_id=current_user.id).first()
    queue = svc.queue_for(current_user)
    recent_closed = (
        SupportConversation.query.filter_by(status=CONV_CLOSED).order_by(SupportConversation.closed_at.desc()).limit(10).all()
        if current_user.can(P.SUPPORT_SUPERVISE)
        else []
    )
    follow_ups = SupportConversation.query.filter_by(consent_follow_up=True, follow_up_done=False).all()
    follow_ups = [c for c in follow_ups if c.agent_id == current_user.id or current_user.can(P.SUPPORT_SUPERVISE)]
    return render_template(
        "workspace/support/queue.html",
        presence=presence,
        queue=queue,
        state=svc.availability(),
        recent_closed=recent_closed,
        follow_ups=follow_ups,
        empty_form=EmptyForm(),
    )


@workspace_bp.route("/support/presence", methods=["POST"])
@staff_required(P.SUPPORT_PRESENCE)
def support_presence():
    if EmptyForm().validate_on_submit():
        try:
            svc.set_presence(current_user, request.form.get("status", "offline"))
        except svc.SupportError as exc:
            flash(t(str(exc)), "error")
    return redirect(url_for("workspace.support_queue"))


@workspace_bp.route("/support/heartbeat", methods=["POST"])
@staff_required(P.SUPPORT_PRESENCE)
def support_heartbeat():
    svc.heartbeat(current_user)
    waiting = SupportConversation.query.filter_by(status="waiting").count()
    return jsonify({"ok": True, "waiting": waiting})


@workspace_bp.route("/support/conversations/<reference>", methods=["GET"])
@any_permission(P.SUPPORT_CHAT, P.SUPPORT_SUPERVISE)
def support_conversation(reference: str):
    conv = _conv(reference)
    if not svc.agent_can_read(conv, current_user):
        abort(403)
    supervising = (
        current_user.can(P.SUPPORT_SUPERVISE)
        and conv.agent_id != current_user.id
        and conv.escalated_to_id != current_user.id
        and conv.status != "waiting"
    )
    if supervising and request.args.get("reason"):
        svc.supervisor_read(conv, current_user, request.args["reason"][:500])
    elif supervising:
        return render_template("workspace/support/supervisor_reason.html", conv=conv, form=ReasonForm())
    linkable = (
        access.queue_query(current_user).filter(Case.status.notin_(("closed", "resolved"))).order_by(Case.created_at.desc()).limit(50).all()
    )
    return render_template(
        "workspace/support/conversation.html",
        conv=conv,
        form=SupportMessageForm(),
        escalate_form=EscalateForm(),
        follow_form=FollowUpForm(obj=conv),
        empty_form=EmptyForm(),
        linkable=linkable,
    )


@workspace_bp.route("/support/conversations/<reference>/reason", methods=["POST"])
@staff_required(P.SUPPORT_SUPERVISE)
def support_supervisor_reason(reference: str):
    conv = _conv(reference)
    form = ReasonForm()
    if form.validate_on_submit():
        return redirect(url_for("workspace.support_conversation", reference=conv.reference, reason=form.reason.data))
    flash(t("access.reason_required"), "error")
    return redirect(url_for("workspace.support_queue"))


@workspace_bp.route("/support/conversations/<reference>/messages")
@any_permission(P.SUPPORT_CHAT, P.SUPPORT_SUPERVISE)
def support_messages(reference: str):
    conv = _conv(reference)
    if not svc.agent_can_read(conv, current_user):
        abort(403)
    after = request.args.get("after", type=int) or 0
    svc.heartbeat(current_user)
    items = [
        {
            "id": m.id,
            "type": m.sender_type,
            "body": t(m.body) if m.sender_type == "system" else m.body,
            "at": m.created_at.strftime("%H:%M"),
        }
        for m in conv.messages
        if m.id > after
    ]
    return jsonify({"status": conv.status, "messages": items})


@workspace_bp.route("/support/conversations/<reference>/accept", methods=["POST"])
@staff_required(P.SUPPORT_CHAT)
def support_accept(reference: str):
    conv = _conv(reference)
    if EmptyForm().validate_on_submit():
        try:
            svc.accept(conv, current_user)
        except svc.SupportError as exc:
            flash(t(str(exc)), "error")
            return redirect(url_for("workspace.support_queue"))
    return redirect(url_for("workspace.support_conversation", reference=conv.reference))


@workspace_bp.route("/support/conversations/<reference>/send", methods=["POST"])
@staff_required(P.SUPPORT_CHAT)
def support_send(reference: str):
    conv = _conv(reference)
    body = (request.form.get("body") or (request.get_json(silent=True) or {}).get("body") or "").strip()
    try:
        msg = svc.agent_message(conv, current_user, body)
    except svc.SupportError as exc:
        if request.is_json:
            return jsonify({"error": t(str(exc))}), 400
        flash(t(str(exc)), "error")
        return redirect(url_for("workspace.support_conversation", reference=conv.reference))
    if request.is_json:
        return jsonify({"id": msg.id})
    return redirect(url_for("workspace.support_conversation", reference=conv.reference))


@workspace_bp.route("/support/conversations/<reference>/escalate", methods=["POST"])
@staff_required(P.SUPPORT_ESCALATE)
def support_escalate(reference: str):
    conv = _conv(reference)
    form = EscalateForm()
    if form.validate_on_submit():
        try:
            svc.escalate(conv, current_user, form.reason.data or "")
            flash(t("support.escalated"), "success")
        except svc.SupportError as exc:
            flash(t(str(exc)), "error")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(url_for("workspace.support_conversation", reference=conv.reference))


@workspace_bp.route("/support/conversations/<reference>/close", methods=["POST"])
@staff_required(P.SUPPORT_CHAT)
def support_close(reference: str):
    conv = _conv(reference)
    if not svc.agent_can_read(conv, current_user):
        abort(403)
    if EmptyForm().validate_on_submit():
        svc.close(conv, by="agent", actor=current_user, reason=request.form.get("reason", "")[:200])
        flash(t("support.closed"), "success")
    return redirect(url_for("workspace.support_queue"))


@workspace_bp.route("/support/conversations/<reference>/follow-up", methods=["POST"])
@staff_required(P.SUPPORT_CHAT)
def support_follow_up(reference: str):
    conv = _conv(reference)
    form = FollowUpForm()
    if form.validate_on_submit():
        try:
            svc.set_follow_up(conv, current_user, bool(form.consent.data), form.note.data)
            if request.form.get("done") == "1":
                conv.follow_up_done = True
                db.session.commit()
            flash(t("support.follow_up_saved"), "success")
        except svc.SupportError as exc:
            flash(t(str(exc)), "error")
    return redirect(url_for("workspace.support_conversation", reference=conv.reference))


@workspace_bp.route("/support/conversations/<reference>/link-case", methods=["POST"])
@staff_required(P.SUPPORT_CHAT)
def support_link_case(reference: str):
    conv = _conv(reference)
    if not svc.agent_can_read(conv, current_user):
        abort(403)
    if EmptyForm().validate_on_submit():
        case = Case.query.filter_by(reference=(request.form.get("case_reference") or "").upper()).first()
        if case is None or not access.can_view_metadata(current_user, case):
            flash(t("support.error_case"), "error")
        else:
            conv.linked_case_id = case.id
            db.session.commit()
            flash(t("support.case_linked"), "success")
    return redirect(url_for("workspace.support_conversation", reference=conv.reference))
