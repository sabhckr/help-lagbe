"""Story review. Moderators and safeguarding supervisors approve, turn down or take down community
stories and replies. Turning something down or taking it off the site needs a written reason."""

from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import permissions as P
from app.extensions import db
from app.forms import StoryDecisionForm
from app.i18n import translate as t
from app.models.story import PENDING, PUBLISHED, REJECTED, Story, StoryReply
from app.routes.workspace import staff_required, workspace_bp
from app.services import stories as story_service
from app.services.security import is_safe_url

STATUSES = (PENDING, PUBLISHED, REJECTED)
# Which decisions make sense from each state.
ALLOWED = {PENDING: ("publish", "reject"), PUBLISHED: ("take_down",), REJECTED: ("publish",)}


@workspace_bp.route("/stories")
@staff_required(P.STORY_MODERATE)
def stories():
    status = request.args.get("status", PENDING)
    if status not in STATUSES:
        status = PENDING
    order = Story.created_at.asc() if status == PENDING else Story.reviewed_at.desc()
    items = Story.query.filter_by(status=status).order_by(order).limit(100).all()
    replies = StoryReply.query.filter_by(status=PENDING).order_by(StoryReply.created_at.asc()).all() if status == PENDING else []
    return render_template(
        "workspace/stories/queue.html",
        items=items,
        replies=replies,
        status=status,
        statuses=STATUSES,
        counts=story_service.pending_counts(),
    )


@workspace_bp.route("/stories/<int:story_id>", methods=["GET", "POST"])
@staff_required(P.STORY_MODERATE)
def story_review(story_id: int):
    story = db.session.get(Story, story_id)
    if story is None:
        abort(404)
    form = StoryDecisionForm()
    form.decision.choices = [(key, f"story.ws_{key}") for key in ALLOWED[story.status]]
    if form.validate_on_submit():
        reason = (form.reason.data or "").strip()
        if form.decision.data in ("reject", "take_down") and len(reason) < 5:
            flash(t("story.ws_reason_required"), "error")
        else:
            story_service.review(story, current_user, form.decision.data, reason)
            flash(t("story.ws_saved"), "success")
            return redirect(url_for("workspace.stories"))
    warnings = story_service.identifier_warnings(story.title, story.body, story.chosen_name, story.image_description)
    return render_template("workspace/stories/review.html", story=story, form=form, warnings=warnings)


@workspace_bp.route("/stories/replies/<int:reply_id>", methods=["POST"])
@staff_required(P.STORY_MODERATE)
def story_reply_review(reply_id: int):
    reply = db.session.get(StoryReply, reply_id)
    if reply is None:
        abort(404)
    form = StoryDecisionForm()
    decision = form.decision.data if form.validate_on_submit() else None
    reason = (form.reason.data or "").strip()
    allowed = ("publish", "reject") if reply.status == PENDING else ("reject",)
    if decision not in allowed:
        flash(t("validation.form_errors"), "error")
    elif decision == "reject" and len(reason) < 5:
        flash(t("story.ws_reason_required"), "error")
    else:
        story_service.review_reply(reply, current_user, str(decision), reason)
        flash(t("story.ws_saved"), "success")
    back = request.form.get("back")
    return redirect(back if back and is_safe_url(back) else url_for("workspace.stories"))


@workspace_bp.route("/stories/replies/<int:reply_id>/story")
@staff_required(P.STORY_MODERATE)
def story_reply_story(reply_id: int):
    """Flags point at a reply id; this opens the story it belongs to."""
    reply = db.session.get(StoryReply, reply_id)
    if reply is None:
        abort(404)
    return redirect(url_for("workspace.story_review", story_id=reply.story_id) + f"#reply-{reply.id}")
