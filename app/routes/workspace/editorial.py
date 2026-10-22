"""Investigations & Editorial: gated publication pipeline, corrections, right of response, social drafts."""

from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import permissions as P
from app.extensions import db
from app.forms import (
    CorrectionForm,
    EmptyForm,
    PublicationForm,
    RedactionForm,
    ReviewForm,
    RightOfResponseForm,
    ShortReasonForm,
    SocialConfirmForm,
    SocialDraftForm,
    add_error,
)
from app.i18n import translate as t
from app.models.case import Case
from app.models.publication import PIPELINE_ORDER, STAGES, Publication, SocialDraft
from app.routes.workspace import any_permission, staff_required, workspace_bp
from app.services import access
from app.services import publication as svc
from app.services.publication import PublicationError
from app.services.redaction import REDACTION_CHECKLIST, scan_for_identifiers


def _pub(pub_id: int) -> Publication:
    pub = db.session.get(Publication, pub_id)
    if pub is None:
        abort(404)
    return pub


def _url(pub: Publication) -> str:
    return url_for("workspace.publication_detail", pub_id=pub.id)


@workspace_bp.route("/publications")
@staff_required(P.PUB_VIEW_PIPELINE)
def publications():
    stage = request.args.get("stage")
    q = Publication.query
    if stage in STAGES:
        q = q.filter_by(stage=stage)
    items = q.order_by(Publication.updated_at.desc()).limit(200).all()
    grouped: dict[str, list[Publication]] = {s: [] for s in STAGES}
    for p in items:
        grouped.setdefault(p.stage, []).append(p)
    return render_template("workspace/editorial/pipeline.html", grouped=grouped, order=PIPELINE_ORDER, stages=STAGES, stage=stage)


@workspace_bp.route("/publications/new", methods=["GET", "POST"])
@staff_required(P.PUB_DRAFT)
def publication_new():
    form = PublicationForm()
    if request.method == "GET" and request.args.get("case"):
        form.case_reference.data = request.args["case"]
    if form.validate_on_submit():
        case = None
        if form.case_reference.data:
            case = Case.query.filter_by(reference=form.case_reference.data.strip().upper()).first()
            if case is None:
                add_error(form.case_reference, "publication.error_case")
                return render_template("workspace/editorial/new.html", form=form)
            if not access.can_view_narrative(current_user, case):
                abort(403)
        try:
            pub = svc.create_draft(current_user, {**form.data, "body": form.body.data, "body_bn": form.body_bn.data}, case=case)
            flash(t("publication.created"), "success")
            return redirect(_url(pub))
        except PublicationError as exc:
            flash(t(str(exc)), "error")
    return render_template("workspace/editorial/new.html", form=form)


@workspace_bp.route("/publications/<int:pub_id>")
@staff_required(P.PUB_VIEW_PIPELINE)
def publication_detail(pub_id: int):
    pub = _pub(pub_id)
    edit_form = PublicationForm(obj=pub)
    edit_form.body.data = pub.body_redacted
    edit_form.body_bn.data = pub.body_redacted_bn
    findings = scan_for_identifiers(pub.headline + "\n" + pub.body_redacted + "\n" + (pub.body_redacted_bn or ""))
    return render_template(
        "workspace/editorial/detail.html",
        pub=pub,
        edit_form=edit_form,
        review_form=ReviewForm(),
        redaction_form=RedactionForm(),
        correction_form=CorrectionForm(),
        ror_form=RightOfResponseForm(),
        social_form=SocialDraftForm(),
        confirm_form=SocialConfirmForm(),
        reason_form=ShortReasonForm(),
        empty_form=EmptyForm(),
        findings=findings,
        checklist=REDACTION_CHECKLIST,
        order=PIPELINE_ORDER,
    )


@workspace_bp.route("/publications/<int:pub_id>/edit", methods=["POST"])
@staff_required(P.PUB_DRAFT)
def publication_edit(pub_id: int):
    pub = _pub(pub_id)
    form = PublicationForm()
    if form.validate_on_submit():
        try:
            svc.update_draft(pub, current_user, {**form.data, "body": form.body.data, "body_bn": form.body_bn.data})
            flash(t("publication.saved"), "success")
        except PublicationError as exc:
            flash(t(str(exc)), "error")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(_url(pub))


@workspace_bp.route("/publications/<int:pub_id>/submit", methods=["POST"])
@staff_required(P.PUB_DRAFT)
def publication_submit(pub_id: int):
    pub = _pub(pub_id)
    if EmptyForm().validate_on_submit():
        try:
            svc.submit_for_review(pub, current_user)
            flash(t("publication.submitted"), "success")
        except PublicationError as exc:
            flash(t(str(exc)), "error")
    return redirect(_url(pub))


@workspace_bp.route("/publications/<int:pub_id>/review/<stage>", methods=["POST"])
@any_permission(P.PUB_SAFETY_REVIEW, P.PUB_SOURCE_REVIEW, P.PUB_EDITORIAL_APPROVE, P.PUB_LEGAL_REVIEW)
def publication_review(pub_id: int, stage: str):
    pub = _pub(pub_id)
    form = ReviewForm()
    if not form.validate_on_submit():
        flash(t("validation.form_errors"), "error")
        return redirect(_url(pub))
    try:
        if stage == "consent_safety_review":
            svc.consent_safety_review(pub, current_user, form.decision.data, form.notes.data or "")
        elif stage == "source_assessment":
            svc.source_review(
                pub,
                current_user,
                form.decision.data,
                form.notes.data or "",
                conflict_checked=bool(form.conflict_checked.data),
                right_of_response=bool(form.right_of_response.data),
            )
        elif stage == "editorial_review":
            svc.editorial_review(pub, current_user, form.decision.data, form.notes.data or "")
        elif stage == "legal_review":
            svc.legal_review(pub, current_user, form.decision.data, form.notes.data or "")
        else:
            abort(404)
        flash(t("publication.review_saved"), "success")
    except PublicationError as exc:
        flash(t(str(exc)), "error")
    return redirect(_url(pub))


@workspace_bp.route("/publications/<int:pub_id>/redaction", methods=["POST"])
@staff_required(P.PUB_REDACT)
def publication_redaction(pub_id: int):
    pub = _pub(pub_id)
    form = RedactionForm()
    if form.validate_on_submit():
        checklist = {k: bool(getattr(form, k).data) for k in REDACTION_CHECKLIST}
        try:
            problems = svc.redaction_check(pub, current_user, checklist, form.notes.data or "")
            if problems:
                flash(t("publication.redaction_failed"), "error")
            else:
                flash(t("publication.redaction_passed"), "success")
        except PublicationError as exc:
            flash(t(str(exc)), "error")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(_url(pub))


@workspace_bp.route("/publications/<int:pub_id>/publish", methods=["POST"])
@staff_required(P.PUB_PUBLISH)
def publication_publish(pub_id: int):
    pub = _pub(pub_id)
    if EmptyForm().validate_on_submit():
        try:
            svc.publish(pub, current_user)
            flash(t("publication.published"), "success")
        except PublicationError as exc:
            flash(t(str(exc)), "error")
    return redirect(_url(pub))


@workspace_bp.route("/publications/<int:pub_id>/withdraw", methods=["POST"])
@staff_required(P.PUB_WITHDRAW)
def publication_withdraw(pub_id: int):
    pub = _pub(pub_id)
    form = ShortReasonForm()
    if form.validate_on_submit():
        try:
            svc.withdraw(pub, current_user, form.reason.data or "")
            flash(t("publication.withdrawn"), "success")
        except PublicationError as exc:
            flash(t(str(exc)), "error")
    else:
        flash(t("access.reason_required"), "error")
    return redirect(_url(pub))


@workspace_bp.route("/publications/<int:pub_id>/correction", methods=["POST"])
@staff_required(P.PUB_CORRECT)
def publication_correction(pub_id: int):
    pub = _pub(pub_id)
    form = CorrectionForm()
    if form.validate_on_submit():
        try:
            svc.add_correction(pub, current_user, form.kind.data, form.text.data or "", form.text_bn.data)
            flash(t("correction.saved"), "success")
        except PublicationError as exc:
            flash(t(str(exc)), "error")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(_url(pub))


@workspace_bp.route("/publications/<int:pub_id>/response", methods=["POST"])
@any_permission(P.PUB_SOURCE_REVIEW, P.PUB_EDITORIAL_APPROVE)
def publication_response(pub_id: int):
    pub = _pub(pub_id)
    form = RightOfResponseForm()
    if form.validate_on_submit():
        try:
            svc.record_right_of_response(
                pub, current_user, form.party_description.data or "", form.response_text.data, bool(form.publish_response.data)
            )
            flash(t("ror.saved"), "success")
        except PublicationError as exc:
            flash(t(str(exc)), "error")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(_url(pub))


@workspace_bp.route("/publications/<int:pub_id>/social", methods=["POST"])
@staff_required(P.SOCIAL_DRAFT)
def social_new(pub_id: int):
    pub = _pub(pub_id)
    form = SocialDraftForm()
    if form.validate_on_submit():
        try:
            svc.create_social_draft(pub, current_user, form.channel.data, form.text.data or "")
            flash(t("social.saved"), "success")
        except PublicationError as exc:
            flash(t(str(exc)), "error")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(_url(pub))


def _draft(draft_id: int) -> SocialDraft:
    draft = db.session.get(SocialDraft, draft_id)
    if draft is None:
        abort(404)
    return draft


@workspace_bp.route("/social/<int:draft_id>/approve", methods=["POST"])
@staff_required(P.SOCIAL_APPROVE)
def social_approve(draft_id: int):
    draft = _draft(draft_id)
    if EmptyForm().validate_on_submit():
        try:
            svc.approve_social_draft(draft, current_user)
            flash(t("social.approved"), "success")
        except PublicationError as exc:
            flash(t(str(exc)), "error")
    return redirect(_url(draft.publication))


@workspace_bp.route("/social/<int:draft_id>/export", methods=["POST"])
@staff_required(P.SOCIAL_DRAFT)
def social_export(draft_id: int):
    draft = _draft(draft_id)
    if EmptyForm().validate_on_submit():
        try:
            svc.mark_exported(draft, current_user)
        except PublicationError as exc:
            flash(t(str(exc)), "error")
            return redirect(_url(draft.publication))
    return render_template("workspace/editorial/social_export.html", draft=draft)


@workspace_bp.route("/social/<int:draft_id>/confirm", methods=["POST"])
@staff_required(P.SOCIAL_CONFIRM)
def social_confirm(draft_id: int):
    draft = _draft(draft_id)
    form = SocialConfirmForm()
    if form.validate_on_submit():
        try:
            svc.confirm_posted(draft, current_user, form.url.data or "")
            flash(t("social.confirmed"), "success")
        except PublicationError as exc:
            flash(t(str(exc)), "error")
    else:
        flash(t("validation.form_errors"), "error")
    return redirect(_url(draft.publication))
