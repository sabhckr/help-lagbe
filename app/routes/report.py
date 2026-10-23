"""Report flow: six short steps. Answers are saved as an encrypted draft at each step; the reference
and one-time key appear only after the database has committed the case."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import report_steps as steps
from app.extensions import limiter
from app.i18n import translate as t
from app.models.draft import DraftFile
from app.models.settings import EmergencyContact
from app.services import audit, drafts
from app.services.drafts import DraftError

report_bp = Blueprint("report", __name__)


def _saved() -> dict:
    return drafts.data(drafts.current())


def _verified_contacts():
    return EmergencyContact.query.filter_by(is_active=True, verified=True).order_by(EmergencyContact.sort_order).all()


def _render(step: int, values, errors: dict | None = None, status: int = 200):
    row = drafts.current()
    files = DraftFile.query.filter_by(draft_id=row.id).order_by(DraftFile.id).all() if row else []
    return render_template(
        "report/step.html",
        step=step,
        values=values,
        errors=errors or {},
        files=files,
        file_limit=drafts.current_limit(),
        contacts=_verified_contacts(),
        total=steps.STEP_COUNT,
    ), status


@report_bp.route("/new")
def new():
    return redirect(url_for("report.step", step=1))


@report_bp.route("/<int:step>", methods=["GET", "POST"])
@limiter.limit("120 per hour", methods=["POST"])
def step(step: int):
    if not 1 <= step <= steps.STEP_COUNT:
        abort(404)
    if step == steps.STEP_COUNT:
        return _review(request.method == "POST")
    if step == 5:
        return _evidence()
    if request.method == "POST":
        values, errors = steps.validate(step, request.form)
        if errors:
            flash(t("validation.form_errors"), "error")
            return _render(step, request.form, errors, 422)
        row = drafts.current() or drafts.start()
        drafts.save(row, values)
        return redirect(url_for("report.step", step=step + 1))
    return _render(step, _saved())


def _evidence():
    if request.method == "GET":
        return _render(5, _saved())
    uploads = [item for item in request.files.getlist("evidence") if item and item.filename]
    if uploads:
        row = drafts.current() or drafts.start()
        refusals = drafts.add_files(row, uploads)
        for filename, key in refusals:
            flash(f"{filename}: {t(key)}", "error")
        if len(refusals) < len(uploads):
            flash(t("report.files_added"), "success")
        return redirect(url_for("report.step", step=5))
    if request.form.get("action") == "back":
        return redirect(url_for("report.step", step=4))
    if drafts.current() is None:
        drafts.start()
    return redirect(url_for("report.step", step=6))


@report_bp.route("/5/remove/<int:file_id>", methods=["POST"])
def remove_file(file_id: int):
    row = drafts.current()
    if row is None or not drafts.remove_file(row, file_id):
        abort(404)
    flash(t("report.file_removed"), "success")
    return redirect(url_for("report.step", step=5))


def _review(submitting: bool):
    values = _saved()
    missing = steps.first_incomplete(values)
    if not submitting:
        if missing is not None and missing != steps.STEP_COUNT:
            return redirect(url_for("report.step", step=missing))
        row = drafts.current()
        files = DraftFile.query.filter_by(draft_id=row.id).order_by(DraftFile.id).all() if row else []
        return render_template(
            "report/step.html",
            step=steps.STEP_COUNT,
            values=values,
            errors={},
            files=files,
            file_limit=drafts.current_limit(),
            contacts=[],
            total=steps.STEP_COUNT,
        ), 200

    if request.form.get("website"):
        # Honeypot filled: almost certainly automated. Refuse without creating anything.
        audit.record("report.honeypot", commit=True)
        flash(t("validation.form_errors"), "error")
        return _render(steps.STEP_COUNT, request.form, {}, 422)
    consent_values, errors = steps.validate(steps.STEP_COUNT, request.form)
    if errors:
        flash(t("validation.form_errors"), "error")
        return _render(steps.STEP_COUNT, request.form, errors, 422)
    row = drafts.current()
    if row is None:
        return redirect(url_for("report.step", step=1))
    drafts.save(row, consent_values)
    try:
        reporter = current_user if current_user.is_authenticated and not current_user.is_staff else None
        drafts.submit(row, reporter_user=reporter)
    except DraftError as exc:
        flash(t(str(exc)), "error")
        return redirect(url_for("report.step", step=steps.STEP_COUNT))
    audit.record("report.submitted", commit=True, details={"via": "draft"})
    return redirect(url_for("report.received"))


@report_bp.route("/received")
def received():
    row = drafts.current()
    receipt = drafts.receipt(row)
    if receipt is None:
        return redirect(url_for("report.step", step=1))
    return render_template("report/received.html", receipt=receipt, contacts=_verified_contacts())


@report_bp.route("/received/dismiss", methods=["POST"])
def dismiss():
    row = drafts.current()
    if row is not None:
        drafts.dismiss(row)
    return redirect(url_for("public.home"))
