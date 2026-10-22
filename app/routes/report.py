"""Report Wrongdoing / Get Help submission flow."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user

from app.extensions import db, limiter
from app.forms import ReportForm
from app.i18n import get_locale
from app.i18n import translate as t
from app.models.base import utcnow
from app.models.settings import EmergencyContact
from app.services import audit
from app.services.cases import CaseError, create_case
from app.services.uploads import UploadError, store_evidence

report_bp = Blueprint("report", __name__)


@report_bp.route("/new", methods=["GET", "POST"])
@limiter.limit("5 per hour; 20 per day", methods=["POST"])
def new():
    form = ReportForm()
    contacts = EmergencyContact.query.filter_by(is_active=True, verified=True).order_by(EmergencyContact.sort_order).all()
    if form.validate_on_submit():
        reporter = current_user if (current_user.is_authenticated and form.submission_type.data == "confidential") else None
        try:
            case, secret = create_case(form.data, reporter_user=reporter, language=get_locale())
        except CaseError as exc:
            flash(t(str(exc)), "error")
            return render_template("report/new.html", form=form, contacts=contacts), 400
        upload_errors: list[str] = []
        stored = 0
        for file in form.evidence.data or []:
            if not file or not file.filename:
                continue
            try:
                store_evidence(case, file, description=form.evidence_description.data)
                stored += 1
            except UploadError as exc:
                upload_errors.append(f"{file.filename}: {t(str(exc))}")
        db.session.commit()
        session["report_receipt"] = {
            "reference": case.reference,
            "secret": secret,
            "safety": case.safety_flag,
            "files": stored,
            "upload_errors": upload_errors,
            "at": utcnow().isoformat(),
        }
        return redirect(url_for("report.submitted"))
    if request.method == "POST":
        flash(t("validation.form_errors"), "error")
    return render_template("report/new.html", form=form, contacts=contacts)


@report_bp.route("/submitted")
def submitted():
    receipt = session.get("report_receipt")
    if not receipt:
        return redirect(url_for("report.new"))
    contacts = EmergencyContact.query.filter_by(is_active=True, verified=True).order_by(EmergencyContact.sort_order).all()
    return render_template("report/submitted.html", receipt=receipt, contacts=contacts)


@report_bp.route("/submitted/dismiss", methods=["POST"])
def dismiss_receipt():
    receipt = session.pop("report_receipt", None)
    if receipt:
        audit.record("report.receipt_dismissed", commit=True)
    return redirect(url_for("public.home"))
