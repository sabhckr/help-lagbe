"""Public site: information pages, published material, requests, PWA assets, language switch."""

from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
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
from app.i18n import translate as t
from app.models.case import Case
from app.models.publication import STAGE_PUBLISHED, Correction, Publication, PublicRequest
from app.models.settings import DepartmentConfig, EmergencyContact, SiteSetting
from app.services import audit
from app.services.publication import new_request_reference
from app.services.security import is_safe_url
from app.services.support import availability

public_bp = Blueprint("public", __name__)

STATIC_PAGES = {
    "get-help": "site/get_help.html",
    "report-wrongdoing": "site/report_wrongdoing.html",
    "awareness": "site/awareness.html",
    "investigations": "site/investigations.html",
    "legal-help": "site/legal_help.html",
    "digital-safety": "site/digital_safety.html",
    "live-support": "site/live_support.html",
    "about": "site/about.html",
    "safeguarding": "site/safeguarding.html",
    "privacy": "site/privacy.html",
    "editorial-policy": "site/editorial_policy.html",
    "corrections": "site/corrections.html",
    "complaints": "site/complaints.html",
    "accessibility": "site/accessibility.html",
    "contact": "site/contact.html",
}


def _contacts():
    return EmergencyContact.query.filter_by(is_active=True).order_by(EmergencyContact.sort_order).all()


def _departments():
    return {d.department: d for d in DepartmentConfig.query.all()}


def _setting(key: str, default: str = "") -> str:
    row = db.session.get(SiteSetting, key)
    return row.value if row else default


@public_bp.route("/")
def home():
    latest = (
        Publication.query.filter_by(stage=STAGE_PUBLISHED)
        .filter(Publication.withdrawn_at.is_(None))
        .order_by(Publication.published_at.desc())
        .limit(3)
        .all()
    )
    return render_template(
        "site/home.html",
        latest=latest,
        availability=availability(),
        contacts=_contacts(),
        announcement=_setting("announcement_" + (request.cookies.get(COOKIE_NAME) or "en")),
    )


@public_bp.route("/<slug>")
def page(slug: str):
    template = STATIC_PAGES.get(slug)
    if not template:
        abort(404)
    ctx = {"contacts": _contacts(), "departments": _departments(), "availability": availability()}
    if slug == "awareness":
        ctx["items"] = (
            Publication.query.filter(
                Publication.stage == STAGE_PUBLISHED, Publication.withdrawn_at.is_(None), Publication.kind.in_(("awareness", "campaign"))
            )
            .order_by(Publication.published_at.desc())
            .all()
        )
    elif slug == "investigations":
        ctx["items"] = (
            Publication.query.filter(
                Publication.stage == STAGE_PUBLISHED, Publication.withdrawn_at.is_(None), Publication.kind.in_(("story", "investigation"))
            )
            .order_by(Publication.published_at.desc())
            .all()
        )
        ctx["verified_outcomes"] = _verified_outcomes()
    elif slug == "corrections":
        ctx["corrections"] = (
            Correction.query.join(Publication)
            .filter(Publication.stage == STAGE_PUBLISHED)
            .order_by(Correction.created_at.desc())
            .limit(50)
            .all()
        )
    return render_template(template, **ctx)


def _verified_outcomes():
    from app.models.case import CaseOutcome

    return CaseOutcome.query.filter_by(verified=True).order_by(CaseOutcome.verified_at.desc()).limit(20).all()


@public_bp.route("/p/<slug>")
def publication(slug: str):
    pub = Publication.query.filter_by(slug=slug).first_or_404()
    if not pub.is_public:
        abort(404)
    return render_template("site/publication.html", pub=pub)


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
    if request.method == "POST":
        flash(t("validation.form_errors"), "error")
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
    """Safe exit: drop tracking/support sessions and leave for a neutral site."""
    session.pop("tracked_cases", None)
    session.pop("support", None)
    session.pop("report_receipt", None)
    return redirect("https://www.google.com/search?q=weather", code=303)
