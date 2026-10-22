"""WTForms definitions. Labels and messages are translation keys resolved in templates."""

from __future__ import annotations

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, MultipleFileField
from wtforms import (
    BooleanField,
    DateField,
    HiddenField,
    IntegerField,
    PasswordField,
    RadioField,
    SelectField,
    StringField,
    TextAreaField,
)
from wtforms.validators import URL, DataRequired, Length, NumberRange, Optional, Regexp

from app import permissions as P
from app.models.case import (
    CONTACT_PREFERENCES,
    FINDING_STATUSES,
    OUTCOME_TYPES,
    REFERRAL_STATUSES,
    REFERRAL_TYPES,
    STATUSES,
)
from app.models.legal import LEGAL_STATUSES
from app.models.moderation import FLAG_REASONS, FLAG_TARGETS
from app.models.publication import PUBLICATION_KINDS, PUBLICATION_LABELS, REQUEST_TYPES, SOCIAL_CHANNELS

REQ = "validation.required"
EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def add_error(field, key: str) -> None:
    field.errors = [*field.errors, key]


def add_errors(field, keys) -> None:
    field.errors = [*field.errors, *keys]


def choices(prefix: str, values) -> list[tuple[str, str]]:
    return [(v, f"{prefix}{v}") for v in values]


# ---- Auth ---------------------------------------------------------------------------------
class LoginForm(FlaskForm):
    email = StringField("auth.email", validators=[DataRequired(REQ), Regexp(EMAIL_RE, message="validation.email"), Length(max=190)])
    password = PasswordField("auth.password", validators=[DataRequired(REQ), Length(max=200)])
    next = HiddenField()


class RegisterForm(FlaskForm):
    name = StringField("auth.name", validators=[DataRequired(REQ), Length(min=2, max=120)])
    email = StringField("auth.email", validators=[DataRequired(REQ), Regexp(EMAIL_RE, message="validation.email"), Length(max=190)])
    password = PasswordField("auth.password", validators=[DataRequired(REQ), Length(max=200)])
    password2 = PasswordField("auth.password_repeat", validators=[DataRequired(REQ)])
    accept = BooleanField("auth.accept_terms", validators=[DataRequired("validation.accept")])


class MfaSetupForm(FlaskForm):
    code = StringField("auth.mfa_code", validators=[DataRequired(REQ), Regexp(r"^\s*\d{6}\s*$", message="validation.mfa_code")])


class MfaVerifyForm(FlaskForm):
    code = StringField("auth.mfa_code", validators=[DataRequired(REQ), Regexp(r"^\s*\d{6}\s*$", message="validation.mfa_code")])


class ChangePasswordForm(FlaskForm):
    current = PasswordField("auth.current_password", validators=[DataRequired(REQ)])
    password = PasswordField("auth.new_password", validators=[DataRequired(REQ), Length(max=200)])
    password2 = PasswordField("auth.password_repeat", validators=[DataRequired(REQ)])


# ---- Reporting ----------------------------------------------------------------------------
class ReportForm(FlaskForm):
    category = SelectField("report.category", choices=choices("category.", P.CATEGORIES), validators=[DataRequired(REQ)])
    title = StringField("report.title", validators=[DataRequired(REQ), Length(min=5, max=200)])
    narrative = TextAreaField("report.narrative", validators=[DataRequired(REQ), Length(min=30, max=20000)])
    approximate_time = StringField("report.approximate_time", validators=[Optional(), Length(max=120)])
    location_text = StringField("report.location", validators=[Optional(), Length(max=200)])
    immediate_danger = RadioField(
        "report.immediate_danger",
        choices=[("no", "report.danger_no"), ("unsure", "report.danger_unsure"), ("yes", "report.danger_yes")],
        default="no",
        validators=[DataRequired(REQ)],
    )
    child_involved = BooleanField("report.child_involved")
    submission_type = RadioField(
        "report.submission_type",
        choices=[("anonymous", "report.type_anonymous"), ("confidential", "report.type_confidential")],
        default="anonymous",
        validators=[DataRequired(REQ)],
    )
    identity_name = StringField("report.identity_name", validators=[Optional(), Length(max=120)])
    identity_phone = StringField("report.identity_phone", validators=[Optional(), Length(max=40)])
    identity_email = StringField(
        "report.identity_email", validators=[Optional(), Regexp(EMAIL_RE, message="validation.email"), Length(max=190)]
    )
    contact_preference = SelectField("report.contact_preference", choices=choices("contact.", CONTACT_PREFERENCES), default="tracking_page")
    safe_contact_notes = TextAreaField("report.safe_contact_notes", validators=[Optional(), Length(max=1000)])
    do_not_contact = StringField("report.do_not_contact", validators=[Optional(), Length(max=300)])
    safe_hours = StringField("report.safe_hours", validators=[Optional(), Length(max=120)])
    evidence = MultipleFileField("report.evidence")
    evidence_description = StringField("report.evidence_description", validators=[Optional(), Length(max=300)])
    consent_process = BooleanField("report.consent_process", validators=[DataRequired("validation.consent")])
    consent_contact = BooleanField("report.consent_contact")
    consent_publication = BooleanField("report.consent_publication")
    website = StringField("website", validators=[Optional(), Length(max=0, message="validation.spam")])


class TrackForm(FlaskForm):
    reference = StringField("track.reference", validators=[DataRequired(REQ), Length(min=10, max=16)])
    secret = StringField("track.secret", validators=[DataRequired(REQ), Length(min=8, max=32)])


class ReporterMessageForm(FlaskForm):
    body = TextAreaField("track.message", validators=[DataRequired(REQ), Length(min=2, max=4000)])


# ---- Case work ------------------------------------------------------------------------------
class SeverityForm(FlaskForm):
    level = RadioField(
        "severity.level",
        choices=[("1", "severity.level1"), ("2", "severity.level2"), ("3", "severity.level3"), ("4", "severity.level4")],
        validators=[DataRequired(REQ)],
    )
    reasoning = TextAreaField("severity.reasoning", validators=[DataRequired(REQ), Length(min=20, max=4000)])
    is_override = BooleanField("severity.is_override")


class StatusForm(FlaskForm):
    to_status = SelectField("case.new_status", choices=choices("status.", STATUSES), validators=[DataRequired(REQ)])
    reason = TextAreaField("case.reason", validators=[DataRequired(REQ), Length(min=10, max=4000)])


class RouteForm(FlaskForm):
    department = SelectField("case.department", choices=choices("dept.", P.DEPARTMENTS), validators=[DataRequired(REQ)])
    reason = TextAreaField("case.reason", validators=[DataRequired(REQ), Length(min=5, max=1000)])


class AssignForm(FlaskForm):
    user_id = SelectField("case.assignee", coerce=int, validators=[DataRequired(REQ)])
    role_in_case = SelectField(
        "case.role_in_case",
        choices=choices("case_role.", ("lead", "specialist", "support", "legal", "cyber", "editorial", "action")),
        default="lead",
    )


class NoteForm(FlaskForm):
    body = TextAreaField("case.note", validators=[DataRequired(REQ), Length(min=2, max=10000)])
    visibility = SelectField(
        "case.visibility", choices=choices("visibility.", ("case_team", "safeguarding", "legal_privileged")), default="case_team"
    )


class ReporterUpdateForm(FlaskForm):
    body = TextAreaField("case.reporter_update", validators=[DataRequired(REQ), Length(min=5, max=4000)])


class ReasonForm(FlaskForm):
    reason = TextAreaField("access.reason", validators=[DataRequired(REQ), Length(min=15, max=1000)])


class ShortReasonForm(FlaskForm):
    reason = TextAreaField("access.reason", validators=[DataRequired(REQ), Length(min=10, max=1000)])


class ReferralForm(FlaskForm):
    referral_type = SelectField("referral.type", choices=choices("referral_type.", REFERRAL_TYPES), validators=[DataRequired(REQ)])
    organisation = StringField("referral.organisation", validators=[DataRequired(REQ), Length(min=2, max=200)])
    consent_obtained = BooleanField("referral.consent_obtained")
    follow_up_due = DateField("referral.follow_up_due", validators=[Optional()])
    notes = TextAreaField("referral.notes", validators=[Optional(), Length(max=4000)])


class ReferralUpdateForm(FlaskForm):
    status = SelectField("referral.status", choices=choices("referral_status.", REFERRAL_STATUSES), validators=[DataRequired(REQ)])
    confirmation_reference = StringField("referral.confirmation", validators=[Optional(), Length(max=200)])
    notes = TextAreaField("referral.notes", validators=[Optional(), Length(max=4000)])


class OutcomeForm(FlaskForm):
    outcome_type = SelectField("outcome.type", choices=choices("outcome_type.", OUTCOME_TYPES), validators=[DataRequired(REQ)])
    finding_status = SelectField("outcome.finding", choices=choices("finding.", FINDING_STATUSES), default="allegation")
    description = TextAreaField("outcome.description", validators=[DataRequired(REQ), Length(min=10, max=4000)])
    confirmation_reference = StringField("outcome.confirmation", validators=[Optional(), Length(max=200)])


class EvidenceUploadForm(FlaskForm):
    file = FileField("evidence.file", validators=[DataRequired(REQ)])
    description = StringField("evidence.description", validators=[Optional(), Length(max=300)])


class CustodyForm(FlaskForm):
    action = SelectField(
        "custody.action",
        choices=choices("custody_action.", ("preserved", "transferred", "hash_verified", "note")),
        validators=[DataRequired(REQ)],
    )
    notes = TextAreaField("custody.notes", validators=[DataRequired(REQ), Length(min=5, max=2000)])


class LegalIntakeForm(FlaskForm):
    matter_type = StringField("legal.matter_type", validators=[DataRequired(REQ), Length(min=3, max=80)])
    status = SelectField("legal.status", choices=choices("legal_status.", LEGAL_STATUSES), default="intake")
    deadline = DateField("legal.deadline", validators=[Optional()])
    deadline_note = StringField("legal.deadline_note", validators=[Optional(), Length(max=255)])
    referral_partner = StringField("legal.referral_partner", validators=[Optional(), Length(max=200)])
    qualified_reviewer = StringField("legal.qualified_reviewer", validators=[Optional(), Length(max=120)])


class FlagForm(FlaskForm):
    target_type = SelectField("moderation.target_type", choices=choices("flag_target.", FLAG_TARGETS), validators=[DataRequired(REQ)])
    target_id = IntegerField("moderation.target_id", validators=[DataRequired(REQ), NumberRange(min=1)])
    reason = SelectField("moderation.reason", choices=choices("flag_reason.", FLAG_REASONS), validators=[DataRequired(REQ)])
    notes = TextAreaField("moderation.notes", validators=[DataRequired(REQ), Length(min=5, max=4000)])


class ModerationActionForm(FlaskForm):
    decision = SelectField(
        "moderation.decision",
        choices=[("actioned", "moderation.actioned"), ("dismissed", "moderation.dismissed")],
        validators=[DataRequired(REQ)],
    )
    action_taken = TextAreaField("moderation.action_taken", validators=[DataRequired(REQ), Length(min=5, max=4000)])
    hold_case = BooleanField("moderation.hold_case")
    mark_spam = BooleanField("moderation.mark_spam")


class AppealDecisionForm(FlaskForm):
    decision = SelectField(
        "moderation.decision",
        choices=[("upheld", "moderation.upheld"), ("rejected", "moderation.rejected")],
        validators=[DataRequired(REQ)],
    )
    notes = TextAreaField("moderation.notes", validators=[DataRequired(REQ), Length(min=5, max=4000)])


# ---- Publication ----------------------------------------------------------------------------
class PublicationForm(FlaskForm):
    kind = SelectField("publication.kind", choices=choices("pub_kind.", PUBLICATION_KINDS), validators=[DataRequired(REQ)])
    label = SelectField("publication.label", choices=choices("pub_label.", PUBLICATION_LABELS), validators=[DataRequired(REQ)])
    headline = StringField("publication.headline", validators=[DataRequired(REQ), Length(min=10, max=200)])
    headline_bn = StringField("publication.headline_bn", validators=[Optional(), Length(max=200)])
    body = TextAreaField("publication.body", validators=[DataRequired(REQ), Length(min=50, max=50000)])
    body_bn = TextAreaField("publication.body_bn", validators=[Optional(), Length(max=50000)])
    legal_review_required = BooleanField("publication.legal_review_required", default=True)
    case_reference = StringField("publication.case_reference", validators=[Optional(), Length(max=16)])


class ReviewForm(FlaskForm):
    decision = SelectField(
        "publication.decision",
        choices=[("approve", "publication.approve"), ("return", "publication.return"), ("reject", "publication.reject")],
        validators=[DataRequired(REQ)],
    )
    notes = TextAreaField("publication.review_notes", validators=[DataRequired(REQ), Length(min=10, max=4000)])
    conflict_checked = BooleanField("publication.conflict_checked")
    right_of_response = BooleanField("publication.right_of_response")


class RedactionForm(FlaskForm):
    no_names = BooleanField("redaction.no_names")
    no_contacts = BooleanField("redaction.no_contacts")
    no_addresses = BooleanField("redaction.no_addresses")
    no_documents = BooleanField("redaction.no_documents")
    no_images_of_people = BooleanField("redaction.no_images_of_people")
    no_child_identifiers = BooleanField("redaction.no_child_identifiers")
    allegation_language = BooleanField("redaction.allegation_language")
    notes = TextAreaField("publication.review_notes", validators=[DataRequired(REQ), Length(min=10, max=4000)])


class CorrectionForm(FlaskForm):
    kind = SelectField(
        "correction.kind",
        choices=[("correction", "correction.correction"), ("clarification", "correction.clarification"), ("update", "correction.update")],
    )
    text = TextAreaField("correction.text", validators=[DataRequired(REQ), Length(min=10, max=4000)])
    text_bn = TextAreaField("correction.text_bn", validators=[Optional(), Length(max=4000)])


class RightOfResponseForm(FlaskForm):
    party_description = StringField("ror.party", validators=[DataRequired(REQ), Length(min=3, max=200)])
    response_text = TextAreaField("ror.response", validators=[Optional(), Length(max=8000)])
    publish_response = BooleanField("ror.publish")


class SocialDraftForm(FlaskForm):
    channel = SelectField("social.channel", choices=choices("channel.", SOCIAL_CHANNELS), validators=[DataRequired(REQ)])
    text = TextAreaField("social.text", validators=[DataRequired(REQ), Length(min=10, max=3000)])


class SocialConfirmForm(FlaskForm):
    url = StringField("social.posted_url", validators=[DataRequired(REQ), URL(message="validation.url"), Length(max=500)])


class PublicRequestForm(FlaskForm):
    request_type = SelectField("request.type", choices=choices("request_type.", REQUEST_TYPES), validators=[DataRequired(REQ)])
    publication_slug = StringField("request.publication", validators=[Optional(), Length(max=80)])
    case_reference = StringField("request.case_reference", validators=[Optional(), Length(max=16)])
    message = TextAreaField("request.message", validators=[DataRequired(REQ), Length(min=20, max=8000)])
    contact = StringField("request.contact", validators=[Optional(), Length(max=200)])
    website = StringField("website", validators=[Optional(), Length(max=0, message="validation.spam")])


class RequestDecisionForm(FlaskForm):
    status = SelectField(
        "request.status", choices=choices("request_status.", ("in_review", "upheld", "rejected", "closed")), validators=[DataRequired(REQ)]
    )
    resolution = TextAreaField("request.resolution", validators=[DataRequired(REQ), Length(min=5, max=4000)])


# ---- Support ----------------------------------------------------------------------------------
class SupportStartForm(FlaskForm):
    topic = SelectField(
        "support.topic", choices=choices("support_topic.", ("safety", "report_help", "legal", "digital", "other")), default="other"
    )
    immediate_danger = BooleanField("support.immediate_danger")
    consent = BooleanField("support.consent", validators=[DataRequired("validation.consent")])


class SupportMessageForm(FlaskForm):
    body = TextAreaField("support.message", validators=[DataRequired(REQ), Length(min=1, max=4000)])


class EscalateForm(FlaskForm):
    reason = TextAreaField("support.escalation_reason", validators=[DataRequired(REQ), Length(min=10, max=2000)])


class FollowUpForm(FlaskForm):
    consent = BooleanField("support.follow_up_consent")
    note = TextAreaField("support.follow_up_note", validators=[Optional(), Length(max=2000)])


# ---- Admin -----------------------------------------------------------------------------------
class StaffUserForm(FlaskForm):
    name = StringField("auth.name", validators=[DataRequired(REQ), Length(min=2, max=120)])
    email = StringField("auth.email", validators=[DataRequired(REQ), Regexp(EMAIL_RE, message="validation.email"), Length(max=190)])
    role = SelectField("admin.role", choices=choices("role.", P.STAFF_ROLES), validators=[DataRequired(REQ)])
    password = PasswordField("auth.temporary_password", validators=[DataRequired(REQ), Length(max=200)])


class RoleForm(FlaskForm):
    role = SelectField("admin.role", choices=choices("role.", P.ALL_ROLES), validators=[DataRequired(REQ)])
    active = BooleanField("admin.active", default=True)
    reason = TextAreaField("case.reason", validators=[DataRequired(REQ), Length(min=5, max=1000)])


class DepartmentConfigForm(FlaskForm):
    is_staffed = BooleanField("admin.is_staffed")
    accepts_cases = BooleanField("admin.accepts_cases", default=True)
    hours_en = StringField("admin.hours_en", validators=[Optional(), Length(max=200)])
    hours_bn = StringField("admin.hours_bn", validators=[Optional(), Length(max=200)])
    notice_en = TextAreaField("admin.notice_en", validators=[Optional(), Length(max=2000)])
    notice_bn = TextAreaField("admin.notice_bn", validators=[Optional(), Length(max=2000)])


class EmergencyContactForm(FlaskForm):
    kind = SelectField(
        "contacts.kind",
        choices=choices("contact_kind.", ("emergency", "police", "women_children", "child", "legal_aid", "counselling", "other")),
        validators=[DataRequired(REQ)],
    )
    name_en = StringField("contacts.name_en", validators=[DataRequired(REQ), Length(max=120)])
    name_bn = StringField("contacts.name_bn", validators=[Optional(), Length(max=120)])
    number = StringField("contacts.number", validators=[DataRequired(REQ), Length(max=40)])
    description_en = TextAreaField("contacts.description_en", validators=[Optional(), Length(max=1000)])
    description_bn = TextAreaField("contacts.description_bn", validators=[Optional(), Length(max=1000)])
    is_active = BooleanField("admin.active", default=True)


class VerifyContactForm(FlaskForm):
    verification_note = StringField("contacts.verification_note", validators=[DataRequired(REQ), Length(min=5, max=255)])


class SettingsForm(FlaskForm):
    mfa_required = BooleanField("admin.mfa_required", default=True)
    public_registration = BooleanField("admin.public_registration", default=True)
    announcement_en = TextAreaField("admin.announcement_en", validators=[Optional(), Length(max=1000)])
    announcement_bn = TextAreaField("admin.announcement_bn", validators=[Optional(), Length(max=1000)])


class EmptyForm(FlaskForm):
    """CSRF-only form for single-button actions."""
