"""Visitor side of Live Human Support."""

from __future__ import annotations

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for

from app.extensions import limiter
from app.forms import SupportMessageForm, SupportStartForm
from app.i18n import get_locale
from app.i18n import translate as t
from app.models.base import utcnow
from app.models.support import CONV_CLOSED
from app.services import support as svc

support_bp = Blueprint("support", __name__)


def _own_conversation(reference: str):
    data = session.get("support") or {}
    if data.get("reference") != reference:
        abort(403)
    conv = svc.visitor_conversation(reference, data.get("token", ""))
    if conv is None:
        abort(403)
    return conv


@support_bp.route("/start", methods=["POST"])
@limiter.limit("5 per hour")
def start():
    form = SupportStartForm()
    if not form.validate_on_submit():
        flash(t("validation.form_errors"), "error")
        return redirect(url_for("public.page", slug="live-support"))
    try:
        conv, token = svc.start_conversation(language=get_locale(), topic=form.topic.data, safety_flag=bool(form.immediate_danger.data))
    except svc.SupportError as exc:
        flash(t(str(exc)), "error")
        return redirect(url_for("public.page", slug="live-support"))
    session["support"] = {"reference": conv.reference, "token": token}
    return redirect(url_for("support.chat", reference=conv.reference))


@support_bp.route("/chat/<reference>")
def chat(reference: str):
    conv = _own_conversation(reference)
    form = SupportMessageForm()
    return render_template("support/chat.html", conv=conv, form=form, availability=svc.availability())


@support_bp.route("/chat/<reference>/messages")
@limiter.limit("120 per minute")
def messages(reference: str):
    conv = _own_conversation(reference)
    after = request.args.get("after", type=int) or 0
    conv.last_visitor_seen_at = utcnow()
    from app.extensions import db

    db.session.commit()
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
    return jsonify(
        {
            "status": conv.status,
            "agent": bool(conv.agent_id),
            "messages": items,
            "waiting_position": _position(conv) if conv.status == "waiting" else None,
        }
    )


def _position(conv) -> int:
    from app.models.support import SupportConversation

    return SupportConversation.query.filter(
        SupportConversation.status == "waiting", SupportConversation.started_at <= conv.started_at
    ).count()


@support_bp.route("/chat/<reference>/send", methods=["POST"])
@limiter.limit("60 per minute")
def send(reference: str):
    conv = _own_conversation(reference)
    body = (request.form.get("body") or (request.get_json(silent=True) or {}).get("body") or "").strip()
    try:
        msg = svc.visitor_message(conv, body)
    except svc.SupportError as exc:
        if request.is_json:
            return jsonify({"error": t(str(exc))}), 400
        flash(t(str(exc)), "error")
        return redirect(url_for("support.chat", reference=reference))
    if request.is_json:
        return jsonify({"id": msg.id})
    return redirect(url_for("support.chat", reference=reference))


@support_bp.route("/chat/<reference>/leave", methods=["POST"])
def leave(reference: str):
    conv = _own_conversation(reference)
    if conv.status != CONV_CLOSED:
        svc.close(conv, by="visitor", reason="visitor left")
    session.pop("support", None)
    return render_template("support/left.html")


@support_bp.route("/status")
def status():
    state = svc.availability()
    return jsonify({k: state[k] for k in ("open", "agents_online", "waiting", "service_enabled")})
