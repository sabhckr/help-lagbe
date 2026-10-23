"""Community stories ("voices"): read, write, preview, react, reply, report, and delete your own.

The write → preview → submit steps keep no server-side draft: the text travels in the form itself,
so an abandoned story leaves nothing behind. Nothing is public until a moderator approves it.
"""

from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, make_response, redirect, render_template, request, session, url_for
from flask_login import current_user

from app import permissions as P
from app.extensions import db, limiter
from app.forms import StoryContentReportForm, StoryForm, StoryManageForm, StoryReplyForm, add_error
from app.i18n import get_locale
from app.i18n import translate as t
from app.models.story import PUBLISHED, STORY_TOPICS, Story, StoryImage, StoryReply
from app.services import stories as story_service

voices_bp = Blueprint("voices", __name__)
PER_PAGE = 12


def _no_store(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def _story_errors(form: StoryForm) -> bool:
    """Checks that depend on more than one field. Returns True when the form can go on."""
    ok = form.validate()
    if (form.website.data or "").strip():
        flash(t("validation.spam"), "error")
        return False
    if form.display_mode.data == "chosen_name" and not (form.chosen_name.data or "").strip():
        add_error(form.chosen_name, "story.error_chosen_name")
        ok = False
    if form.display_mode.data == "account_name" and not current_user.is_authenticated:
        add_error(form.display_mode, "story.error_account_name")
        ok = False
    return ok


@voices_bp.route("/")
def index():
    topic = request.args.get("topic")
    query = Story.query.filter_by(status=PUBLISHED)
    if topic in STORY_TOPICS:
        query = query.filter_by(topic=topic)
    else:
        topic = None
    page = max(request.args.get("page", 1, type=int), 1)
    items = query.order_by(Story.published_at.desc()).offset((page - 1) * PER_PAGE).limit(PER_PAGE + 1).all()
    return render_template(
        "voices/index.html", stories=items[:PER_PAGE], topic=topic, topics=STORY_TOPICS, page=page, has_next=len(items) > PER_PAGE
    )


@voices_bp.route("/new", methods=["GET", "POST"])
@limiter.limit("60 per hour", methods=["POST"])
def new():
    form = StoryForm()
    if request.method == "POST":
        if request.form.get("action") == "edit":
            return _no_store(make_response(render_template("voices/new.html", form=form)))
        if _story_errors(form):
            warnings = story_service.identifier_warnings(
                form.title.data, form.body.data, form.chosen_name.data, form.image_description.data
            )
            return _no_store(make_response(render_template("voices/preview.html", form=form, warnings=warnings)))
        flash(t("validation.form_errors"), "error")
    return _no_store(make_response(render_template("voices/new.html", form=form)))


@voices_bp.route("/submit", methods=["POST"])
@limiter.limit("5 per hour")
def submit():
    form = StoryForm()
    ok = _story_errors(form)
    if not form.reviewed.data:
        add_error(form.reviewed, "story.error_reviewed")
        ok = False
    files = [f for f in request.files.getlist(form.images.name) if f and f.filename]
    if len(files) > current_app.config["STORY_MAX_IMAGES"]:
        add_error(form.images, "story.image_error_count")
        ok = False
    warnings = story_service.identifier_warnings(form.title.data, form.body.data, form.chosen_name.data, form.image_description.data)
    if not ok:
        return _no_store(make_response(render_template("voices/preview.html", form=form, warnings=warnings), 422))
    try:
        story, code = story_service.create(
            form.data, files, author=current_user if current_user.is_authenticated else None, language=get_locale()
        )
    except story_service.StoryImageError as exc:
        add_error(form.images, str(exc))
        return _no_store(make_response(render_template("voices/preview.html", form=form, warnings=warnings), 422))
    return _no_store(make_response(render_template("voices/received.html", story=story, code=code)))


@voices_bp.route("/<reference>")
def detail(reference: str):
    story = Story.query.filter_by(reference=reference.upper(), status=PUBLISHED).first_or_404()
    return render_template(
        "voices/detail.html",
        story=story,
        reply_form=StoryReplyForm(),
        report_form=StoryContentReportForm(),
        reacted=story_service.reacted(story, session),
    )


@voices_bp.route("/<reference>/react", methods=["POST"])
@limiter.limit("60 per hour")
def react(reference: str):
    story = Story.query.filter_by(reference=reference.upper(), status=PUBLISHED).first_or_404()
    StoryReplyForm()  # CSRF is checked globally; nothing else is needed from the form
    if story_service.react(story, request.form.get("kind", ""), session):
        flash(t("story.reaction_thanks"), "success")
    return redirect(url_for("voices.detail", reference=story.reference) + "#support")


@voices_bp.route("/<reference>/reply", methods=["POST"])
@limiter.limit("10 per hour")
def reply(reference: str):
    story = Story.query.filter_by(reference=reference.upper(), status=PUBLISHED).first_or_404()
    if story.reply_mode == "off":
        flash(t("story.replies_off"), "error")
        return redirect(url_for("voices.detail", reference=story.reference))
    form = StoryReplyForm()
    if (form.website.data or "").strip():
        flash(t("validation.spam"), "error")
    elif form.validate():
        story_service.add_reply(story, form.body.data or "", form.display_name.data)
        flash(t("story.reply_sent"), "success")
    else:
        flash(t(form.body.errors[0] if form.body.errors else "validation.form_errors"), "error")
    return redirect(url_for("voices.detail", reference=story.reference) + "#replies")


@voices_bp.route("/report", methods=["POST"])
@limiter.limit("10 per hour")
def report():
    form = StoryContentReportForm()
    if not form.validate():
        abort(400)
    if form.target.data == "story":
        story = Story.query.filter_by(id=form.target_id.data, status=PUBLISHED).first_or_404()
    else:
        item = db.session.get(StoryReply, form.target_id.data)
        if item is None or item.status != PUBLISHED or item.story.status != PUBLISHED:
            abort(404)
        story = item.story
    story_service.report(form.target.data or "story", int(form.target_id.data or 0), form.reason.data or "other", form.notes.data)
    flash(t("story.report_sent"), "success")
    return redirect(url_for("voices.detail", reference=story.reference))


@voices_bp.route("/manage", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def manage():
    form = StoryManageForm()
    story = None
    if request.method == "POST" and form.validate():
        story = story_service.find_for_writer(form.reference.data or "", form.code.data or "")
        if story is None:
            flash(t("story.manage_not_found"), "error")
        elif request.form.get("action") == "delete":
            if request.form.get("confirm") != "y":
                flash(t("story.manage_confirm_needed"), "error")
            else:
                story_service.delete_by_writer(story)
                return _no_store(make_response(render_template("voices/manage.html", form=StoryManageForm(formdata=None), deleted=True)))
    return _no_store(make_response(render_template("voices/manage.html", form=form, story=story, deleted=False)))


@voices_bp.route("/image/<int:image_id>")
def image(image_id: int):
    item = db.session.get(StoryImage, image_id)
    if item is None:
        abort(404)
    public = item.story.status == PUBLISHED
    if not public and not (current_user.is_authenticated and current_user.can(P.STORY_MODERATE)):
        abort(404)
    response = make_response(story_service.image_bytes(item))
    response.headers["Content-Type"] = item.mime_type
    response.headers["Content-Disposition"] = "inline"
    response.headers["Cache-Control"] = "public, max-age=3600" if public else "no-store"
    return response
