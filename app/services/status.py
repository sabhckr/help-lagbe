"""Public case status. Internal workflow states collapse into five plain states for the reporter."""

from __future__ import annotations

from app.models.case import (
    STATUS_CLOSED,
    STATUS_NEEDS_INFORMATION,
    STATUS_RESOLVED,
    STATUS_SUBMITTED,
    STATUS_TRIAGE,
)

PUBLIC_RECEIVED = "received"
PUBLIC_REVIEW = "under_review"
PUBLIC_MORE_INFO = "more_information"
PUBLIC_REFERRED = "referred"
PUBLIC_CLOSED = "closed"
PUBLIC_STATES = (PUBLIC_RECEIVED, PUBLIC_REVIEW, PUBLIC_MORE_INFO, PUBLIC_REFERRED, PUBLIC_CLOSED)

REFERRAL_ACTIVE = ("accepted", "submitted", "confirmed")


def public_state(case) -> str:
    """Closed wins; then more information; then a real referral; then received or under review."""
    if case.status in (STATUS_RESOLVED, STATUS_CLOSED):
        return PUBLIC_CLOSED
    if case.status == STATUS_NEEDS_INFORMATION:
        return PUBLIC_MORE_INFO
    if any(r.status in REFERRAL_ACTIVE for r in case.referrals):
        return PUBLIC_REFERRED
    if case.status in (STATUS_SUBMITTED, STATUS_TRIAGE):
        return PUBLIC_RECEIVED
    return PUBLIC_REVIEW


def public_state_for_internal(internal_status: str) -> str:
    """The public state a timeline entry shows, without referral context."""
    if internal_status in (STATUS_RESOLVED, STATUS_CLOSED):
        return PUBLIC_CLOSED
    if internal_status == STATUS_NEEDS_INFORMATION:
        return PUBLIC_MORE_INFO
    if internal_status in (STATUS_SUBMITTED, STATUS_TRIAGE):
        return PUBLIC_RECEIVED
    return PUBLIC_REVIEW
