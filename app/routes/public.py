"""Public site: home, help, stories, about, safety, privacy, contact, language switch, PWA assets."""

from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_login import current_user, login_required

from app.crypto import encrypt_json
from app.extensions import db, limiter
from app.forms import PublicRequestForm
from app.i18n import COOKIE_NAME
from app.models.case import Case
from app.models.publication import STAGE_PUBLISHED, Correction, Publication, PublicRequest
from app.models.settings import DepartmentConfig, EmergencyContact, SiteSetting
from app.models.story import PUBLISHED as STORY_PUBLISHED
from app.models.story import STORY_TOPICS, Story
from app.services import audit
from app.services.publication import new_request_reference
from app.services.security import is_safe_url
from app.services.support import availability

public_bp = Blueprint("public", __name__)

STORY_KINDS = ("story", "investigation", "awareness", "campaign")


def _verified_contacts():
    return EmergencyContact.query.filter_by(is_active=True, verified=True).order_by(EmergencyContact.sort_order).all()


def _setting(key: str, default: str = "") -> str:
    row = db.session.get(SiteSetting, key)
    return row.value if row else default


def _published():
    return Publication.query.filter(
        Publication.stage == STAGE_PUBLISHED,
        Publication.withdrawn_at.is_(None),
        Publication.kind.in_(STORY_KINDS),
    ).order_by(Publication.published_at.desc())


@public_bp.route("/")
def home():
    latest = _published().limit(3).all()
    stories = Story.query.filter_by(status=STORY_PUBLISHED).order_by(Story.published_at.desc()).limit(3).all()
    return render_template(
        "site/home.html",
        latest=latest,
        stories=stories,
        topics=STORY_TOPICS,
        availability=availability(),
        announcement=_setting("announcement_" + (request.cookies.get(COOKIE_NAME) or current_app.config["DEFAULT_LANGUAGE"])),
    )


@public_bp.route("/help")
def help_page():
    departments = {d.department: d for d in DepartmentConfig.query.all()}
    from app.forms import SupportStartForm

    state = availability()
    return render_template(
        "site/help.html",
        availability=state,
        contacts=_verified_contacts(),
        departments=departments,
        support_form=SupportStartForm() if state["open"] else None,
    )


@public_bp.route("/stories")
def stories():
    items = _published().all()
    corrections = (
        Correction.query.join(Publication)
        .filter(Publication.stage == STAGE_PUBLISHED)
        .order_by(Correction.created_at.desc())
        .limit(30)
        .all()
    )
    return render_template("site/stories.html", items=items, corrections=corrections)


@public_bp.route("/stories/<slug>")
def story(slug: str):
    pub = Publication.query.filter_by(slug=slug).first_or_404()
    if not pub.is_public:
        abort(404)
    return render_template("site/story.html", pub=pub)


@public_bp.route("/about")
def about():
    return render_template("site/about.html")


@public_bp.route("/accountability")
def accountability():
    return render_template("site/accountability.html", latest=_published().limit(3).all())


@public_bp.route("/safety")
def safety():
    return render_template("site/safety.html")


@public_bp.route("/privacy")
def privacy():
    return render_template("site/privacy.html")


@public_bp.route("/contact")
def contact():
    return render_template("site/contact.html")


@public_bp.route("/requests/new", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def new_request():
    form = PublicRequestForm()
    if request.method == "GET" and request.args.get("type") in [c[0] for c in (form.request_type.choices or [])]:
        form.request_type.data = request.args.get("type")
        form.publication_slug.data = request.args.get("publication", "")
    if form.validate_on_submit():
        pub = Publication.query.filter_by(slug=(form.publication_slug.data or "").strip()).first() if form.publication_slug.data else None
        req = PublicRequest(
            reference=new_request_reference(),
            request_type=form.request_type.data,
            publication_id=pub.id if pub else None,
            case_reference=(form.case_reference.data or "").strip() or None,
            message=(form.message.data or "").strip(),
            contact_enc=encrypt_json({"contact": form.contact.data.strip()}) if form.contact.data else None,
        )
        db.session.add(req)
        db.session.flush()
        audit.record("request.created", target_type="public_request", target_id=req.id, details={"type": req.request_type})
        db.session.commit()
        return render_template("site/request_submitted.html", reference=req.reference)
    return render_template("site/request_new.html", form=form)


@public_bp.route("/my-reports")
@login_required
def my_reports():
    if current_user.is_staff:
        return redirect(url_for("workspace.home"))
    cases = Case.query.filter_by(reporter_user_id=current_user.id).order_by(Case.created_at.desc()).all()
    return render_template("site/my_reports.html", cases=cases)


@public_bp.route("/lang/<code>")
def set_language(code: str):
    if code not in current_app.config["LANGUAGES"]:
        abort(404)
    target = request.args.get("next") or request.referrer or url_for("public.home")
    if not is_safe_url(target):
        target = url_for("public.home")
    resp = make_response(redirect(target))
    resp.set_cookie(
        COOKIE_NAME,
        code,
        max_age=60 * 60 * 24 * 365,
        samesite="Lax",
        httponly=True,
        secure=current_app.config.get("SESSION_COOKIE_SECURE", False),
    )
    if current_user.is_authenticated:
        current_user.preferred_lang = code
        db.session.commit()
    return resp


@public_bp.route("/offline")
def offline():
    return render_template("site/offline.html")


@public_bp.route("/sw.js")
def service_worker():
    resp = send_from_directory(current_app.static_folder or "static", "sw.js", mimetype="application/javascript")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@public_bp.route("/manifest.webmanifest")
def manifest():
    return send_from_directory(current_app.static_folder or "static", "manifest.webmanifest", mimetype="application/manifest+json")


@public_bp.route("/healthz")
def healthz():
    try:
        db.session.execute(db.text("SELECT 1"))
        return jsonify({"status": "ok"})
    except Exception:  # noqa: BLE001
        return jsonify({"status": "degraded"}), 503


@public_bp.route("/quick-exit", methods=["POST", "GET"])
def quick_exit():
    """Leave quickly: drop reporting and tracking state from this session, then go to a neutral page."""
    session.pop("tracked_cases", None)
    session.pop("support", None)
    session.pop("report_draft", None)
    return redirect("https://www.google.com/search?q=weather", code=303)
