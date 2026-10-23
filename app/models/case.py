from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Model
from app.models.base import random_reference, utcnow

if TYPE_CHECKING:
    from app.models.evidence import Evidence
    from app.models.identity import ReporterIdentity
    from app.models.legal import LegalIntake
    from app.models.publication import Publication

# ---- Vocabulary ------------------------------------------------------------------------------
STATUS_SUBMITTED = "submitted"
STATUS_TRIAGE = "triage"
STATUS_ASSIGNED = "assigned"
STATUS_UNDER_REVIEW = "under_review"
STATUS_SPECIALIST_REVIEW = "specialist_review"
STATUS_REFERRAL_ACTION = "referral_action"
STATUS_FOLLOW_UP = "follow_up"
STATUS_RESOLVED = "resolved"
STATUS_CLOSED = "closed"
STATUS_APPEALED = "appealed"
STATUS_REOPENED = "reopened"
STATUS_NEEDS_INFORMATION = "needs_information"

STATUSES = (
    STATUS_SUBMITTED,
    STATUS_TRIAGE,
    STATUS_ASSIGNED,
    STATUS_UNDER_REVIEW,
    STATUS_SPECIALIST_REVIEW,
    STATUS_REFERRAL_ACTION,
    STATUS_FOLLOW_UP,
    STATUS_RESOLVED,
    STATUS_CLOSED,
    STATUS_APPEALED,
    STATUS_REOPENED,
    STATUS_NEEDS_INFORMATION,
)
OPEN_STATUSES = tuple(s for s in STATUSES if s not in (STATUS_RESOLVED, STATUS_CLOSED))

# Allowed lifecycle transitions. Anything not listed is refused server-side.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    STATUS_SUBMITTED: (STATUS_TRIAGE, STATUS_CLOSED),
    STATUS_TRIAGE: (STATUS_ASSIGNED, STATUS_UNDER_REVIEW, STATUS_CLOSED),
    STATUS_ASSIGNED: (STATUS_UNDER_REVIEW, STATUS_TRIAGE, STATUS_CLOSED, STATUS_NEEDS_INFORMATION),
    STATUS_UNDER_REVIEW: (STATUS_SPECIALIST_REVIEW, STATUS_REFERRAL_ACTION, STATUS_RESOLVED, STATUS_TRIAGE, STATUS_NEEDS_INFORMATION),
    STATUS_NEEDS_INFORMATION: (STATUS_UNDER_REVIEW, STATUS_CLOSED),
    STATUS_SPECIALIST_REVIEW: (STATUS_UNDER_REVIEW, STATUS_REFERRAL_ACTION, STATUS_RESOLVED),
    STATUS_REFERRAL_ACTION: (STATUS_FOLLOW_UP, STATUS_RESOLVED, STATUS_UNDER_REVIEW),
    STATUS_FOLLOW_UP: (STATUS_RESOLVED, STATUS_REFERRAL_ACTION),
    STATUS_RESOLVED: (STATUS_CLOSED, STATUS_REOPENED),
    STATUS_CLOSED: (STATUS_APPEALED, STATUS_REOPENED),
    STATUS_APPEALED: (STATUS_REOPENED, STATUS_CLOSED),
    STATUS_REOPENED: (STATUS_UNDER_REVIEW, STATUS_ASSIGNED),
}

SEVERITY_LEVELS = {
    1: "severity.level1",
    2: "severity.level2",
    3: "severity.level3",
    4: "severity.level4",
}

SUBMISSION_ANONYMOUS = "anonymous"
SUBMISSION_CONFIDENTIAL = "confidential"

DANGER_YES, DANGER_NO, DANGER_UNSURE = "yes", "no", "unsure"

CONTACT_NONE = "none"
CONTACT_TRACKING = "tracking_page"
CONTACT_PHONE = "phone"
CONTACT_EMAIL = "email"
CONTACT_PREFERENCES = (CONTACT_NONE, CONTACT_TRACKING, CONTACT_PHONE, CONTACT_EMAIL)

OUTCOME_TYPES = (
    "referral_offered",
    "complaint_submitted",
    "platform_action_confirmed",
    "official_outcome_verified",
    "investigation_ongoing",
    "outcome_unknown",
)
FINDING_STATUSES = (
    "allegation",
    "under_official_investigation",
    "charged",
    "convicted",
    "acquitted",
    "dismissed",
    "official_finding",
    "not_applicable",
    "unknown",
)
REFERRAL_TYPES = ("legal_aid", "counselling", "medical", "police", "child_protection", "ngo", "platform", "institution", "other")
REFERRAL_STATUSES = ("offered", "accepted", "declined", "submitted", "confirmed", "closed")


class Case(Model):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True, default=random_reference)
    tracking_secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    approximate_time: Mapped[str | None] = mapped_column(String(120), nullable=True)
    location_text: Mapped[str | None] = mapped_column(String(200), nullable=True)

    submission_type: Mapped[str] = mapped_column(String(16), nullable=False, default=SUBMISSION_ANONYMOUS)
    has_identity: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reporter_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)

    immediate_danger: Mapped[str] = mapped_column(String(8), nullable=False, default=DANGER_UNSURE)
    child_involved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    safety_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    child_safety_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    consent_process: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consent_publication: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consent_contact: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    contact_preference: Mapped[str] = mapped_column(String(20), nullable=False, default=CONTACT_TRACKING)
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")

    severity_level: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=STATUS_SUBMITTED, index=True)
    department: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    is_spam: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    moderation_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    retention_review_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    assignments: Mapped[list[CaseAssignment]] = relationship(back_populates="case", cascade="all, delete-orphan")
    notes: Mapped[list[CaseNote]] = relationship(back_populates="case", cascade="all, delete-orphan", order_by="CaseNote.created_at")
    status_changes: Mapped[list[StatusChange]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="StatusChange.created_at"
    )
    severity_assessments: Mapped[list[SeverityAssessment]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="SeverityAssessment.created_at"
    )
    updates: Mapped[list[CaseUpdate]] = relationship(back_populates="case", cascade="all, delete-orphan", order_by="CaseUpdate.created_at")
    referrals: Mapped[list[Referral]] = relationship(back_populates="case", cascade="all, delete-orphan")
    outcomes: Mapped[list[CaseOutcome]] = relationship(back_populates="case", cascade="all, delete-orphan")
    identity: Mapped[ReporterIdentity | None] = relationship(back_populates="case", uselist=False, cascade="all, delete-orphan")
    evidence: Mapped[list[Evidence]] = relationship(back_populates="case", cascade="all, delete-orphan")
    legal_intake: Mapped[LegalIntake | None] = relationship(back_populates="case", uselist=False, cascade="all, delete-orphan")
    publications: Mapped[list[Publication]] = relationship(back_populates="case", cascade="all, delete-orphan")

    # ---- helpers ---------------------------------------------------------------------------
    @property
    def is_anonymous(self) -> bool:
        return self.submission_type == SUBMISSION_ANONYMOUS

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    @property
    def severity_key(self) -> str:
        return SEVERITY_LEVELS.get(self.severity_level or 0, "severity.unassessed")

    def active_assignee_ids(self) -> set[int]:
        return {a.user_id for a in self.assignments if a.active}

    def is_assigned_to(self, user_id: int) -> bool:
        return user_id in self.active_assignee_ids()

    def can_transition_to(self, new_status: str) -> bool:
        return new_status in TRANSITIONS.get(self.status, ())

    def __repr__(self) -> str:
        return f"<Case {self.reference} status={self.status}>"


class CaseAssignment(Model):
    __tablename__ = "case_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    assigned_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    role_in_case: Mapped[str] = mapped_column(String(32), nullable=False, default="lead")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    case: Mapped[Case] = relationship(back_populates="assignments")
    user = relationship("User", foreign_keys=[user_id])
    assigned_by = relationship("User", foreign_keys=[assigned_by_id])


NOTE_VISIBILITY_TEAM = "case_team"
NOTE_VISIBILITY_LEGAL = "legal_privileged"
NOTE_VISIBILITY_SAFEGUARDING = "safeguarding"


class CaseNote(Model):
    __tablename__ = "case_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    note_type: Mapped[str] = mapped_column(String(32), nullable=False, default="note")
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default=NOTE_VISIBILITY_TEAM)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    case: Mapped[Case] = relationship(back_populates="notes")
    author = relationship("User")


class StatusChange(Model):
    __tablename__ = "case_status_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    case: Mapped[Case] = relationship(back_populates="status_changes")
    actor = relationship("User")


class SeverityAssessment(Model):
    __tablename__ = "case_severity_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    assessor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    previous_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)  # initial | escalation | de_escalation | reaffirmed
    is_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    case: Mapped[Case] = relationship(back_populates="severity_assessments")
    assessor = relationship("User")


class CaseUpdate(Model):
    """A message from the case team to the reporter, shown on the tracking page.
    Never contains identity; never sent anywhere automatically."""

    __tablename__ = "case_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="message")  # message | status
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    case: Mapped[Case] = relationship(back_populates="updates")
    author = relationship("User")


class Referral(Model):
    __tablename__ = "case_referrals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    referral_type: Mapped[str] = mapped_column(String(32), nullable=False)
    organisation: Mapped[str] = mapped_column(String(200), nullable=False)
    consent_obtained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="offered")
    confirmation_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    case: Mapped[Case] = relationship(back_populates="referrals")
    owner = relationship("User")


class CaseOutcome(Model):
    __tablename__ = "case_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    recorded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    outcome_type: Mapped[str] = mapped_column(String(40), nullable=False)
    finding_status: Mapped[str] = mapped_column(String(40), nullable=False, default="allegation")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    confirmation_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    case: Mapped[Case] = relationship(back_populates="outcomes")
    recorded_by = relationship("User", foreign_keys=[recorded_by_id])
    verified_by = relationship("User", foreign_keys=[verified_by_id])
