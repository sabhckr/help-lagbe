"""Track My Case: reference + one-time secret, no account needed, no identity shown."""

from __future__ import annotations

import hmac
import re

from flask import Blueprint, abort, flash, redirect, render_template, session, url_for

from app.crypto import hash_secret
from app.extensions import db, limiter
from app.forms import ReporterMessageForm, TrackForm
from app.i18n import translate as t
from app.models.base import utcnow
from app.models.case import Case
from app.services import audit
from app.services.cases import CaseError, add_reporter_message

track_bp = Blueprint("track", __name__)


def normalise_reference(raw: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9]", "", (raw or "").upper().replace("O", "0"))
    if len(cleaned) == 10 and cleaned.startswith("HL"):
        return f"HL-{cleaned[2:6]}-{cleaned[6:]}"
    return cleaned


def _unlocked(reference: str) -> bool:
    return reference in (session.get("tracked_cases") or {})


def _require(reference: str) -> Case:
    if not _unlocked(reference):
        abort(403)
    case = Case.query.filter_by(reference=reference).first()
    if case is None:
        abort(404)
    return case


@track_bp.route("/", methods=["GET", "POST"])
@limiter.limit("10 per minute; 60 per hour", methods=["POST"])
def index():
    form = TrackForm()
    if form.validate_on_submit():
        reference = normalise_reference(form.reference.data or "")
        secret = re.sub(r"[^A-Z0-9]", "", (form.secret.data or "").upper())
        case = Case.query.filter_by(reference=reference).first()
        expected = case.tracking_secret_hash if case else hash_secret("x")
        if case is not None and hmac.compare_digest(expected, hash_secret(secret)):
            tracked = dict(session.get("tracked_cases") or {})
            tracked[reference] = utcnow().isoformat()
            session["tracked_cases"] = tracked
            audit.record("track.opened", target_type="case", target_id=case.id, case_id=case.id, commit=True)
            return redirect(url_for("track.view", reference=reference))
        audit.record("track.failed", commit=True)
        flash(t("track.not_found"), "error")
    return render_template("track/index.html", form=form)


@track_bp.route("/<reference>")
def view(reference: str):
    case = _require(reference)
    form = ReporterMessageForm()
    timeline = [u for u in case.updates]
    referrals = [r for r in case.referrals]
    outcomes = [o for o in case.outcomes]
    return render_template("track/view.html", case=case, form=form, timeline=timeline, referrals=referrals, outcomes=outcomes)


@track_bp.route("/<reference>/message", methods=["POST"])
@limiter.limit("20 per hour")
def message(reference: str):
    case = _require(reference)
    form = ReporterMessageForm()
    if form.validate_on_submit():
        try:
            add_reporter_message(case, form.body.data or "")
            flash(t("track.message_sent"), "success")
        except CaseError as exc:
            flash(t(str(exc)), "error")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(url_for("track.view", reference=reference))


@track_bp.route("/<reference>/forget", methods=["POST"])
def forget(reference: str):
    tracked = dict(session.get("tracked_cases") or {})
    tracked.pop(reference, None)
    session["tracked_cases"] = tracked
    flash(t("track.forgotten"), "success")
    return redirect(url_for("track.index"))


@track_bp.route("/forget-all", methods=["POST"])
def forget_all():
    session.pop("tracked_cases", None)
    db.session.rollback()
    return redirect(url_for("public.home"))
