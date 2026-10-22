"""Gated publication pipeline.

submission → consent & safety review → source/evidence assessment → redaction → editorial review
→ legal review (when required) → approved → published → corrections / appeals / withdrawal.

Every gate is a separate recorded decision by a named person; the drafter cannot approve
their own piece; publishing requires every gate to be green. Nothing here posts anywhere."""

from __future__ import annotations

import re
import secrets
from typing import Any

from app import permissions as P
from app.extensions import db
from app.models.base import random_reference, utcnow
from app.models.case import Case
from app.models.publication import (
    LABEL_ALLEGATION,
    LABEL_AWARENESS,
    PUBLICATION_KINDS,
    PUBLICATION_LABELS,
    SOCIAL_CHANNELS,
    STAGE_APPROVED,
    STAGE_CONSENT_SAFETY,
    STAGE_DRAFT,
    STAGE_EDITORIAL,
    STAGE_LEGAL,
    STAGE_PUBLISHED,
    STAGE_REDACTION,
    STAGE_REJECTED,
    STAGE_SOURCE,
    STAGE_WITHDRAWN,
    Correction,
    Publication,
    PublicationReview,
    RightOfResponse,
    SocialDraft,
)
from app.services import audit
from app.services.redaction import REDACTION_CHECKLIST, scan_for_identifiers


class PublicationError(ValueError):
    pass


def _slugify(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:50] or "story"
    return f"{base}-{secrets.token_hex(3)}"


def create_draft(user, data: dict[str, Any], *, case: Case | None = None) -> Publication:
    kind = data.get("kind") or "story"
    if kind not in PUBLICATION_KINDS:
        raise PublicationError("publication.error_kind")
    label = data.get("label") or (LABEL_AWARENESS if kind in ("awareness", "campaign") else LABEL_ALLEGATION)
    if label not in PUBLICATION_LABELS:
        raise PublicationError("publication.error_label")
    headline = (data.get("headline") or "").strip()
    if len(headline) < 10:
        raise PublicationError("publication.error_headline")
    if case is not None and not case.consent_publication:
        raise PublicationError("publication.error_no_consent")
    pub = Publication(
        case_id=case.id if case else None,
        slug=_slugify(headline),
        kind=kind,
        label=label,
        headline=headline,
        headline_bn=(data.get("headline_bn") or "").strip() or None,
        body_redacted=(data.get("body") or "").strip(),
        body_redacted_bn=(data.get("body_bn") or "").strip() or None,
        drafted_by_id=user.id,
        stage=STAGE_DRAFT,
        legal_review_required=(kind in ("story", "investigation")),
    )
    db.session.add(pub)
    db.session.flush()
    audit.record(
        "publication.draft",
        actor=user,
        target_type="publication",
        target_id=pub.id,
        case_id=pub.case_id,
        details={"kind": kind, "label": label},
    )
    db.session.commit()
    return pub


def update_draft(pub: Publication, user, data: dict[str, Any]) -> None:
    if pub.stage in (STAGE_PUBLISHED, STAGE_WITHDRAWN):
        raise PublicationError("publication.error_locked")
    pub.headline = (data.get("headline") or pub.headline).strip()
    pub.headline_bn = (data.get("headline_bn") or "").strip() or None
    pub.body_redacted = (data.get("body") or "").strip()
    pub.body_redacted_bn = (data.get("body_bn") or "").strip() or None
    if data.get("label") in PUBLICATION_LABELS:
        pub.label = data["label"]
    pub.legal_review_required = bool(data.get("legal_review_required", pub.legal_review_required))
    # Any edit after a gate invalidates redaction + editorial + legal sign-off.
    pub.redaction_done = False
    pub.editorial_approved = False
    pub.legal_reviewed = False
    if pub.stage in (STAGE_EDITORIAL, STAGE_LEGAL, STAGE_APPROVED):
        pub.stage = STAGE_REDACTION
    audit.record("publication.edited", actor=user, target_type="publication", target_id=pub.id, case_id=pub.case_id)
    db.session.commit()


def submit_for_review(pub: Publication, user) -> None:
    if pub.stage != STAGE_DRAFT:
        raise PublicationError("publication.error_stage")
    if len(pub.body_redacted) < 50:
        raise PublicationError("publication.error_body")
    pub.stage = STAGE_CONSENT_SAFETY
    _review(pub, user, STAGE_DRAFT, "approve", "Submitted for consent and safety review")
    db.session.commit()


def _review(pub: Publication, user, stage: str, decision: str, notes: str) -> PublicationReview:
    notes = (notes or "").strip()
    if len(notes) < 10:
        raise PublicationError("publication.error_notes")
    review = PublicationReview(publication_id=pub.id, reviewer_id=user.id, stage=stage, decision=decision, notes=notes)
    db.session.add(review)
    audit.record(
        f"publication.{stage}", actor=user, target_type="publication", target_id=pub.id, case_id=pub.case_id, details={"decision": decision}
    )
    return review


def consent_safety_review(pub: Publication, user, decision: str, notes: str) -> None:
    if pub.stage != STAGE_CONSENT_SAFETY:
        raise PublicationError("publication.error_stage")
    if not user.can(P.PUB_SAFETY_REVIEW):
        raise PublicationError("publication.error_permission")
    if decision == "approve":
        if pub.case is not None and not pub.case.consent_publication:
            raise PublicationError("publication.error_no_consent")
        if pub.case is not None and pub.case.child_safety_flag and pub.label != LABEL_AWARENESS:
            # Child-safety cases are never published as case stories.
            raise PublicationError("publication.error_child_safety")
        pub.consent_verified = True
        pub.safety_reviewed = True
        pub.stage = STAGE_SOURCE
    elif decision == "reject":
        pub.stage = STAGE_REJECTED
    else:
        pub.stage = STAGE_DRAFT
    _review(pub, user, STAGE_CONSENT_SAFETY, decision, notes)
    db.session.commit()


def source_review(pub: Publication, user, decision: str, notes: str, *, conflict_checked: bool, right_of_response: bool) -> None:
    if pub.stage != STAGE_SOURCE:
        raise PublicationError("publication.error_stage")
    if not user.can(P.PUB_SOURCE_REVIEW):
        raise PublicationError("publication.error_permission")
    if user.id == pub.drafted_by_id:
        raise PublicationError("publication.error_two_person")
    if decision == "approve":
        if not conflict_checked:
            raise PublicationError("publication.error_conflict")
        if pub.label != LABEL_AWARENESS and not right_of_response:
            raise PublicationError("publication.error_right_of_response")
        pub.source_reviewed = True
        pub.conflict_of_interest_checked = True
        pub.right_of_response_offered = right_of_response
        pub.stage = STAGE_REDACTION
    elif decision == "reject":
        pub.stage = STAGE_REJECTED
    else:
        pub.stage = STAGE_DRAFT
    _review(pub, user, STAGE_SOURCE, decision, notes)
    db.session.commit()


def redaction_check(pub: Publication, user, checklist: dict[str, bool], notes: str) -> list:
    if pub.stage != STAGE_REDACTION:
        raise PublicationError("publication.error_stage")
    if not user.can(P.PUB_REDACT):
        raise PublicationError("publication.error_permission")
    findings = scan_for_identifiers(pub.headline + "\n" + pub.body_redacted + "\n" + (pub.body_redacted_bn or ""))
    missing = [k for k in REDACTION_CHECKLIST if not checklist.get(k)]
    if findings or missing:
        _review(pub, user, STAGE_REDACTION, "return", notes or "Automatic identifier scan or checklist failed")
        db.session.commit()
        return findings + [type("Missing", (), {"kind": "checklist", "sample": m})() for m in missing]
    pub.redaction_done = True
    pub.redaction_checklist = ",".join(REDACTION_CHECKLIST)
    pub.stage = STAGE_EDITORIAL
    _review(pub, user, STAGE_REDACTION, "approve", notes)
    db.session.commit()
    return []


def editorial_review(pub: Publication, user, decision: str, notes: str) -> None:
    if pub.stage != STAGE_EDITORIAL:
        raise PublicationError("publication.error_stage")
    if not user.can(P.PUB_EDITORIAL_APPROVE):
        raise PublicationError("publication.error_permission")
    if user.id == pub.drafted_by_id:
        raise PublicationError("publication.error_two_person")
    if decision == "approve":
        pub.editorial_approved = True
        pub.approved_by_id = user.id
        pub.stage = STAGE_LEGAL if pub.legal_review_required else STAGE_APPROVED
    elif decision == "reject":
        pub.stage = STAGE_REJECTED
    else:
        pub.stage = STAGE_REDACTION
        pub.redaction_done = False
    _review(pub, user, STAGE_EDITORIAL, decision, notes)
    db.session.commit()


def legal_review(pub: Publication, user, decision: str, notes: str) -> None:
    if pub.stage != STAGE_LEGAL:
        raise PublicationError("publication.error_stage")
    if not user.can(P.PUB_LEGAL_REVIEW):
        raise PublicationError("publication.error_permission")
    if decision == "approve":
        pub.legal_reviewed = True
        pub.stage = STAGE_APPROVED
    elif decision == "reject":
        pub.stage = STAGE_REJECTED
    else:
        pub.stage = STAGE_REDACTION
        pub.redaction_done = False
        pub.editorial_approved = False
    _review(pub, user, STAGE_LEGAL, decision, notes)
    db.session.commit()


def publish(pub: Publication, user) -> None:
    if not user.can(P.PUB_PUBLISH):
        raise PublicationError("publication.error_permission")
    if not pub.ready_to_publish():
        raise PublicationError("publication.error_gates")
    if scan_for_identifiers(pub.headline + "\n" + pub.body_redacted + "\n" + (pub.body_redacted_bn or "")):
        raise PublicationError("publication.error_identifiers")
    pub.stage = STAGE_PUBLISHED
    pub.published_by_id = user.id
    pub.published_at = utcnow()
    _review(pub, user, STAGE_APPROVED, "approve", "Published after all gates passed")
    audit.record("publication.published", actor=user, target_type="publication", target_id=pub.id, case_id=pub.case_id)
    db.session.commit()


def withdraw(pub: Publication, user, reason: str) -> None:
    if not user.can(P.PUB_WITHDRAW):
        raise PublicationError("publication.error_permission")
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise PublicationError("publication.error_notes")
    pub.stage = STAGE_WITHDRAWN
    pub.withdrawn_at = utcnow()
    pub.withdrawn_reason = reason
    audit.record("publication.withdrawn", actor=user, target_type="publication", target_id=pub.id, case_id=pub.case_id, reason=reason)
    db.session.commit()


def add_correction(pub: Publication, user, kind: str, text: str, text_bn: str | None = None) -> Correction:
    if not user.can(P.PUB_CORRECT):
        raise PublicationError("publication.error_permission")
    if kind not in ("correction", "clarification", "update"):
        kind = "correction"
    text = (text or "").strip()
    if len(text) < 10:
        raise PublicationError("publication.error_notes")
    if scan_for_identifiers(text):
        raise PublicationError("publication.error_identifiers")
    correction = Correction(publication_id=pub.id, author_id=user.id, kind=kind, text=text, text_bn=(text_bn or "").strip() or None)
    db.session.add(correction)
    audit.record("publication.correction", actor=user, target_type="publication", target_id=pub.id, case_id=pub.case_id)
    db.session.commit()
    return correction


def record_right_of_response(pub: Publication, user, party: str, response_text: str | None, publish_response: bool) -> RightOfResponse:
    party = (party or "").strip()
    if not party:
        raise PublicationError("validation.required")
    ror = RightOfResponse(
        publication_id=pub.id,
        recorded_by_id=user.id,
        party_description=party,
        response_text=(response_text or "").strip() or None,
        received_at=utcnow() if response_text else None,
        publish_response=publish_response,
    )
    db.session.add(ror)
    pub.right_of_response_offered = True
    audit.record("publication.right_of_response", actor=user, target_type="publication", target_id=pub.id, case_id=pub.case_id)
    db.session.commit()
    return ror


# ---- Social media: prepared and exported by humans, never auto-posted ------------------------
def create_social_draft(pub: Publication, user, channel: str, text: str) -> SocialDraft:
    if not user.can(P.SOCIAL_DRAFT):
        raise PublicationError("publication.error_permission")
    if not pub.is_public:
        raise PublicationError("social.error_not_published")
    if channel not in SOCIAL_CHANNELS:
        raise PublicationError("social.error_channel")
    text = (text or "").strip()
    if len(text) < 10:
        raise PublicationError("publication.error_notes")
    if scan_for_identifiers(text):
        raise PublicationError("publication.error_identifiers")
    draft = SocialDraft(publication_id=pub.id, channel=channel, text=text, drafted_by_id=user.id)
    db.session.add(draft)
    audit.record("social.draft", actor=user, target_type="social_draft", target_id=None, case_id=pub.case_id, details={"channel": channel})
    db.session.commit()
    return draft


def approve_social_draft(draft: SocialDraft, user) -> None:
    if not user.can(P.SOCIAL_APPROVE):
        raise PublicationError("publication.error_permission")
    if draft.drafted_by_id == user.id:
        raise PublicationError("publication.error_two_person")
    if draft.status != "drafted":
        raise PublicationError("publication.error_stage")
    draft.status = "approved"
    draft.approved_by_id = user.id
    audit.record("social.approved", actor=user, target_type="social_draft", target_id=draft.id, case_id=draft.publication.case_id)
    db.session.commit()


def mark_exported(draft: SocialDraft, user) -> None:
    if draft.status != "approved":
        raise PublicationError("publication.error_stage")
    draft.status = "exported"
    audit.record("social.exported", actor=user, target_type="social_draft", target_id=draft.id, case_id=draft.publication.case_id)
    db.session.commit()


def confirm_posted(draft: SocialDraft, user, url: str) -> None:
    """Only a human who has seen the live post may mark it posted, and must give the URL."""
    if not user.can(P.SOCIAL_CONFIRM):
        raise PublicationError("publication.error_permission")
    url = (url or "").strip()
    if draft.status not in ("approved", "exported") or not re.match(r"^https://", url):
        raise PublicationError("social.error_confirm")
    draft.status = "posted_confirmed"
    draft.posted_url = url[:500]
    draft.posted_confirmed_by_id = user.id
    draft.posted_confirmed_at = utcnow()
    audit.record("social.posted_confirmed", actor=user, target_type="social_draft", target_id=draft.id, case_id=draft.publication.case_id)
    db.session.commit()


def new_request_reference() -> str:
    return random_reference("RQ")
