from __future__ import annotations

from flask import render_template
from flask_login import current_user

from app import permissions as P
from app.models.case import OPEN_STATUSES, STATUS_SUBMITTED, STATUS_TRIAGE, Case
from app.models.moderation import ModerationFlag
from app.models.publication import PIPELINE_ORDER, STAGE_PUBLISHED, STAGE_WITHDRAWN, Publication, PublicRequest
from app.models.settings import DepartmentConfig
from app.models.support import AgentPresence
from app.routes.workspace import staff_required, workspace_bp
from app.services import access
from app.services import support as support_svc


@workspace_bp.route("/")
@staff_required(P.WORKSPACE)
def home():
    visible = access.queue_query(current_user)
    stats = {
        "open": visible.filter(Case.status.in_(OPEN_STATUSES)).count(),
        "intake": visible.filter(Case.status.in_((STATUS_SUBMITTED, STATUS_TRIAGE))).count(),
        "safety": visible.filter(Case.safety_flag.is_(True), Case.status.in_(OPEN_STATUSES)).count(),
        "mine": Case.query.filter(Case.id.in_([a.case_id for a in current_user_assignments()]), Case.status.in_(OPEN_STATUSES)).count(),
        "unassessed": visible.filter(Case.severity_level.is_(None), Case.status.in_(OPEN_STATUSES)).count(),
    }
    recent = visible.filter(Case.status.in_(OPEN_STATUSES)).order_by(Case.safety_flag.desc(), Case.created_at.desc()).limit(8).all()
    dept_cfg = DepartmentConfig.query.filter_by(department=current_user.department).first() if current_user.department else None
    presence = AgentPresence.query.filter_by(user_id=current_user.id).first() if current_user.can(P.SUPPORT_PRESENCE) else None
    pipeline = None
    if current_user.can(P.PUB_VIEW_PIPELINE):
        pipeline = {
            stage: Publication.query.filter_by(stage=stage).count()
            for stage in PIPELINE_ORDER
            if stage not in (STAGE_PUBLISHED, STAGE_WITHDRAWN)
        }
    mod_open = ModerationFlag.query.filter_by(status="open").count() if current_user.can(P.MOD_QUEUE) else None
    requests_open = PublicRequest.query.filter_by(status="open").count() if current_user.can_any(P.MOD_QUEUE, P.PUB_CORRECT) else None
    support_state = support_svc.availability() if current_user.can_any(P.SUPPORT_CHAT, P.ADMIN_CONFIG) else None
    return render_template(
        "workspace/home.html",
        stats=stats,
        recent=recent,
        dept_cfg=dept_cfg,
        presence=presence,
        pipeline=pipeline,
        mod_open=mod_open,
        requests_open=requests_open,
        support_state=support_state,
    )


def current_user_assignments():
    from app.models.case import CaseAssignment

    return CaseAssignment.query.filter_by(user_id=current_user.id, active=True).all()
