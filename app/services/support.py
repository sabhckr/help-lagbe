"""Live human support: real presence, truthful availability, queue, private conversations,
escalation, safe exit and consented follow-up. No simulated agents, no fake wait times."""

from __future__ import annotations

from datetime import timedelta

from flask import current_app

from app import permissions as P
from app.crypto import hash_secret
from app.extensions import db
from app.models.base import random_reference, random_secret, utcnow
from app.models.settings import DepartmentConfig
from app.models.support import (
    CONV_ACTIVE,
    CONV_CLOSED,
    CONV_WAITING,
    PRESENCE_AVAILABLE,
    PRESENCE_BUSY,
    PRESENCE_OFFLINE,
    AgentPresence,
    SupportConversation,
    SupportMessage,
)
from app.models.user import User
from app.services import audit


class SupportError(ValueError):
    pass


def _timeout() -> timedelta:
    return timedelta(seconds=current_app.config.get("SUPPORT_PRESENCE_TIMEOUT_SECONDS", 120))


def set_presence(user, status: str) -> AgentPresence:
    if status not in (PRESENCE_AVAILABLE, PRESENCE_BUSY, PRESENCE_OFFLINE):
        raise SupportError("support.error_status")
    if not user.can(P.SUPPORT_PRESENCE):
        raise SupportError("support.error_permission")
    presence = AgentPresence.query.filter_by(user_id=user.id).first()
    if presence is None:
        presence = AgentPresence(user_id=user.id)
        db.session.add(presence)
    presence.status = status
    presence.last_seen_at = utcnow()
    db.session.commit()
    return presence


def heartbeat(user) -> None:
    presence = AgentPresence.query.filter_by(user_id=user.id).first()
    if presence is not None and presence.status != PRESENCE_OFFLINE:
        presence.last_seen_at = utcnow()
        db.session.commit()


def available_agents() -> list[AgentPresence]:
    cutoff = utcnow() - _timeout()
    return (
        AgentPresence.query.join(User, User.id == AgentPresence.user_id)
        .filter(AgentPresence.status == PRESENCE_AVAILABLE, AgentPresence.last_seen_at >= cutoff, User.active.is_(True))
        .all()
    )


def department_config(department: str) -> DepartmentConfig | None:
    return DepartmentConfig.query.filter_by(department=department).first()


def availability() -> dict:
    """What the public is told. Truthful by construction: `agents_online` is a live count."""
    cfg = department_config(P.DEPT_SUPPORT)
    agents = available_agents()
    waiting = SupportConversation.query.filter_by(status=CONV_WAITING).count()
    staffed = bool(cfg and cfg.is_staffed)
    return {
        "service_enabled": staffed,
        "agents_online": len(agents),
        "waiting": waiting,
        "open": staffed and len(agents) > 0,
        "hours_en": cfg.hours_en if cfg else None,
        "hours_bn": cfg.hours_bn if cfg else None,
        "notice_en": cfg.notice_en if cfg else None,
        "notice_bn": cfg.notice_bn if cfg else None,
    }


def start_conversation(*, language: str, topic: str | None, safety_flag: bool) -> tuple[SupportConversation, str]:
    state = availability()
    if not state["open"]:
        raise SupportError("support.error_closed")
    token = random_secret(24)
    conv = SupportConversation(
        reference=random_reference("SC"),
        token_hash=hash_secret(token),
        status=CONV_WAITING,
        language=language,
        topic=(topic or None),
        safety_flag=safety_flag,
        visitor_label=f"Visitor {random_secret(4)}",
    )
    db.session.add(conv)
    db.session.flush()
    db.session.add(SupportMessage(conversation_id=conv.id, sender_type="system", body="support.msg_waiting"))
    audit.record("support.started", target_type="conversation", target_id=conv.id, details={"safety_flag": safety_flag})
    db.session.commit()
    return conv, token


def visitor_conversation(reference: str, token: str) -> SupportConversation | None:
    conv = SupportConversation.query.filter_by(reference=reference).first()
    if conv is None or conv.token_hash != hash_secret(token or ""):
        return None
    return conv


def visitor_message(conv: SupportConversation, body: str) -> SupportMessage:
    body = (body or "").strip()
    if not body or len(body) > 4000:
        raise SupportError("validation.required")
    if conv.status == CONV_CLOSED:
        raise SupportError("support.error_closed_conv")
    msg = SupportMessage(conversation_id=conv.id, sender_type="visitor", body=body)
    conv.last_visitor_seen_at = utcnow()
    db.session.add(msg)
    db.session.commit()
    return msg


def accept(conv: SupportConversation, agent) -> None:
    if not agent.can(P.SUPPORT_CHAT):
        raise SupportError("support.error_permission")
    if conv.status != CONV_WAITING:
        raise SupportError("support.error_not_waiting")
    conv.status = CONV_ACTIVE
    conv.agent_id = agent.id
    conv.accepted_at = utcnow()
    db.session.add(SupportMessage(conversation_id=conv.id, sender_type="system", body="support.msg_agent_joined"))
    presence = AgentPresence.query.filter_by(user_id=agent.id).first()
    if presence:
        presence.status = PRESENCE_BUSY
    audit.record("support.accepted", actor=agent, target_type="conversation", target_id=conv.id)
    db.session.commit()


def agent_can_read(conv: SupportConversation, user) -> bool:
    if user.can(P.SUPPORT_SUPERVISE):
        return True
    return user.can(P.SUPPORT_CHAT) and (conv.agent_id == user.id or conv.escalated_to_id == user.id or conv.status == CONV_WAITING)


def agent_message(conv: SupportConversation, agent, body: str) -> SupportMessage:
    if not agent_can_read(conv, agent) or conv.status != CONV_ACTIVE:
        raise SupportError("support.error_permission")
    if conv.agent_id != agent.id and conv.escalated_to_id != agent.id and not agent.can(P.SUPPORT_SUPERVISE):
        raise SupportError("support.error_permission")
    body = (body or "").strip()
    if not body or len(body) > 4000:
        raise SupportError("validation.required")
    msg = SupportMessage(conversation_id=conv.id, sender_type="agent", sender_id=agent.id, body=body)
    db.session.add(msg)
    db.session.commit()
    return msg


def escalate(conv: SupportConversation, agent, reason: str) -> None:
    if not agent.can(P.SUPPORT_ESCALATE) or conv.agent_id != agent.id:
        raise SupportError("support.error_permission")
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise SupportError("support.error_reason")
    supervisor = User.query.filter(User.role == P.ROLE_SUPERVISOR, User.active.is_(True)).first()
    conv.escalated_to_id = supervisor.id if supervisor else None
    conv.escalated_at = utcnow()
    conv.escalation_reason = reason
    conv.safety_flag = True
    db.session.add(SupportMessage(conversation_id=conv.id, sender_type="system", body="support.msg_escalated"))
    audit.record(
        "support.escalated",
        actor=agent,
        target_type="conversation",
        target_id=conv.id,
        reason=reason,
        details={"supervisor_found": supervisor is not None},
    )
    db.session.commit()


def close(conv: SupportConversation, *, by: str, actor=None, reason: str | None = None) -> None:
    if conv.status == CONV_CLOSED:
        return
    conv.status = CONV_CLOSED
    conv.closed_at = utcnow()
    conv.closed_by = by
    conv.close_reason = (reason or "")[:200] or None
    if conv.agent_id:
        presence = AgentPresence.query.filter_by(user_id=conv.agent_id).first()
        if presence and presence.status == PRESENCE_BUSY:
            presence.status = PRESENCE_AVAILABLE
    db.session.add(SupportMessage(conversation_id=conv.id, sender_type="system", body="support.msg_closed"))
    audit.record("support.closed", actor=actor, target_type="conversation", target_id=conv.id, details={"by": by})
    db.session.commit()


def set_follow_up(conv: SupportConversation, agent, consent: bool, note: str | None) -> None:
    if conv.agent_id != agent.id and not agent.can(P.SUPPORT_SUPERVISE):
        raise SupportError("support.error_permission")
    conv.consent_follow_up = consent
    conv.follow_up_note = (note or "").strip() or None if consent else None
    audit.record("support.follow_up_set", actor=agent, target_type="conversation", target_id=conv.id, details={"consent": consent})
    db.session.commit()


def supervisor_read(conv: SupportConversation, user, reason: str) -> None:
    """Supervisors reading a conversation they are not part of must say why; it is logged."""
    audit.record("support.supervisor_read", actor=user, target_type="conversation", target_id=conv.id, reason=reason, commit=True)


def queue_for(user) -> list[SupportConversation]:
    q = SupportConversation.query.filter(SupportConversation.status != CONV_CLOSED)
    if user.can(P.SUPPORT_SUPERVISE):
        return q.order_by(SupportConversation.safety_flag.desc(), SupportConversation.started_at).all()
    return (
        q.filter(
            (SupportConversation.status == CONV_WAITING)
            | (SupportConversation.agent_id == user.id)
            | (SupportConversation.escalated_to_id == user.id)
        )
        .order_by(SupportConversation.safety_flag.desc(), SupportConversation.started_at)
        .all()
    )


def expire_abandoned(minutes: int = 30) -> int:
    cutoff = utcnow() - timedelta(minutes=minutes)
    stale = SupportConversation.query.filter(
        SupportConversation.status != CONV_CLOSED, SupportConversation.last_visitor_seen_at < cutoff
    ).all()
    for conv in stale:
        close(conv, by="system", reason="visitor inactive")
    return len(stale)
