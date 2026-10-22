from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Model, db
from app.models.base import utcnow

STAGE_DRAFT = "draft"
STAGE_CONSENT_SAFETY = "consent_safety_review"
STAGE_SOURCE = "source_assessment"
STAGE_REDACTION = "redaction"
STAGE_EDITORIAL = "editorial_review"
STAGE_LEGAL = "legal_review"
STAGE_APPROVED = "approved"
STAGE_PUBLISHED = "published"
STAGE_WITHDRAWN = "withdrawn"
STAGE_REJECTED = "rejected"

STAGES = (
    STAGE_DRAFT,
    STAGE_CONSENT_SAFETY,
    STAGE_SOURCE,
    STAGE_REDACTION,
    STAGE_EDITORIAL,
    STAGE_LEGAL,
    STAGE_APPROVED,
    STAGE_PUBLISHED,
    STAGE_WITHDRAWN,
    STAGE_REJECTED,
)
PIPELINE_ORDER = (
    STAGE_DRAFT,
    STAGE_CONSENT_SAFETY,
    STAGE_SOURCE,
    STAGE_REDACTION,
    STAGE_EDITORIAL,
    STAGE_LEGAL,
    STAGE_APPROVED,
    STAGE_PUBLISHED,
)

# What the public is told the piece is. Never "guilty".
LABEL_ALLEGATION = "reported_allegation"
LABEL_CORROBORATED = "corroborated_finding"
LABEL_OFFICIAL = "official_statement"
LABEL_COURT = "court_established_outcome"
LABEL_AWARENESS = "awareness_material"
PUBLICATION_LABELS = (LABEL_ALLEGATION, LABEL_CORROBORATED, LABEL_OFFICIAL, LABEL_COURT, LABEL_AWARENESS)

KIND_STORY = "story"
KIND_INVESTIGATION = "investigation"
KIND_AWARENESS = "awareness"
KIND_CAMPAIGN = "campaign"
PUBLICATION_KINDS = (KIND_STORY, KIND_INVESTIGATION, KIND_AWARENESS, KIND_CAMPAIGN)


class Publication(Model):
    __tablename__ = "publications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"), nullable=True, index=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default=KIND_STORY)
    label: Mapped[str] = mapped_column(String(32), nullable=False, default=LABEL_ALLEGATION)
    headline: Mapped[str] = mapped_column(String(200), nullable=False)
    headline_bn: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body_redacted: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body_redacted_bn: Mapped[str | None] = mapped_column(Text, nullable=True)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default=STAGE_DRAFT, index=True)

    consent_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    safety_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    redaction_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    redaction_checklist: Mapped[str | None] = mapped_column(Text, nullable=True)
    editorial_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    legal_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    legal_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    right_of_response_offered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    conflict_of_interest_checked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    drafted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    published_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    withdrawn_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    case = relationship("Case", back_populates="publications")
    drafted_by = relationship("User", foreign_keys=[drafted_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    published_by = relationship("User", foreign_keys=[published_by_id])
    reviews: Mapped[list[PublicationReview]] = relationship(
        back_populates="publication", cascade="all, delete-orphan", order_by="PublicationReview.created_at"
    )
    corrections: Mapped[list[Correction]] = relationship(
        back_populates="publication", cascade="all, delete-orphan", order_by="Correction.created_at"
    )
    responses: Mapped[list[RightOfResponse]] = relationship(back_populates="publication", cascade="all, delete-orphan")
    social_drafts: Mapped[list[SocialDraft]] = relationship(back_populates="publication", cascade="all, delete-orphan")

    @property
    def is_public(self) -> bool:
        return self.stage == STAGE_PUBLISHED and self.withdrawn_at is None

    def gates_passed(self) -> dict[str, bool]:
        return {
            "consent_verified": self.consent_verified,
            "safety_reviewed": self.safety_reviewed,
            "source_reviewed": self.source_reviewed,
            "conflict_of_interest_checked": self.conflict_of_interest_checked,
            "redaction_done": self.redaction_done,
            "editorial_approved": self.editorial_approved,
            "legal_reviewed": (self.legal_reviewed or not self.legal_review_required),
        }

    def ready_to_publish(self) -> bool:
        return all(self.gates_passed().values()) and self.stage == STAGE_APPROVED


class PublicationReview(Model):
    __tablename__ = "publication_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publication_id: Mapped[int] = mapped_column(ForeignKey("publications.id"), nullable=False, index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)  # approve | return | reject
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    publication: Mapped[Publication] = relationship(back_populates="reviews")
    reviewer = relationship("User")


class Correction(Model):
    __tablename__ = "publication_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publication_id: Mapped[int] = mapped_column(ForeignKey("publications.id"), nullable=False, index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="correction")  # correction | clarification | update
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_bn: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    publication: Mapped[Publication] = relationship(back_populates="corrections")
    author = relationship("User")


class RightOfResponse(Model):
    __tablename__ = "publication_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publication_id: Mapped[int] = mapped_column(ForeignKey("publications.id"), nullable=False, index=True)
    recorded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    party_description: Mapped[str] = mapped_column(String(200), nullable=False)  # e.g. "the institution named"
    offered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    publish_response: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    publication: Mapped[Publication] = relationship(back_populates="responses")
    recorded_by = relationship("User")


REQUEST_TYPES = ("correction", "appeal", "removal", "complaint", "right_of_reply")


class PublicRequest(Model):
    """Correction / appeal / removal / complaint submitted from the public site."""

    __tablename__ = "public_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    request_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    publication_id: Mapped[int | None] = mapped_column(ForeignKey("publications.id"), nullable=True)
    case_reference: Mapped[str | None] = mapped_column(String(16), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    contact_enc: Mapped[bytes | None] = mapped_column(db.LargeBinary, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", index=True
    )  # open | in_review | upheld | rejected | closed
    handled_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    publication = relationship("Publication")
    handled_by = relationship("User")


SOCIAL_CHANNELS = ("facebook", "instagram", "reddit", "x", "other")
SOCIAL_STATUSES = ("drafted", "approved", "exported", "posted_confirmed", "cancelled")


class SocialDraft(Model):
    __tablename__ = "social_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publication_id: Mapped[int] = mapped_column(ForeignKey("publications.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="drafted")
    drafted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    posted_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    posted_confirmed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    posted_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    publication: Mapped[Publication] = relationship(back_populates="social_drafts")
    drafted_by = relationship("User", foreign_keys=[drafted_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    posted_confirmed_by = relationship("User", foreign_keys=[posted_confirmed_by_id])
