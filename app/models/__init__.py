"""All ORM models. Importing this package registers every table with SQLAlchemy."""

from app.models.audit import AuditEvent
from app.models.case import (
    Case,
    CaseAssignment,
    CaseNote,
    CaseOutcome,
    CaseUpdate,
    Referral,
    SeverityAssessment,
    StatusChange,
)
from app.models.draft import DraftFile, ReportDraft
from app.models.evidence import CustodyRecord, Evidence
from app.models.identity import ReporterIdentity
from app.models.legal import LegalIntake
from app.models.moderation import ModerationAppeal, ModerationFlag
from app.models.publication import (
    Correction,
    Publication,
    PublicationReview,
    PublicRequest,
    RightOfResponse,
    SocialDraft,
)
from app.models.settings import DepartmentConfig, EmergencyContact, SiteSetting
from app.models.support import AgentPresence, SupportConversation, SupportMessage
from app.models.user import User

__all__ = [
    "DraftFile",
    "ReportDraft",
    "AuditEvent",
    "Case",
    "CaseAssignment",
    "CaseNote",
    "CaseOutcome",
    "CaseUpdate",
    "Referral",
    "SeverityAssessment",
    "StatusChange",
    "CustodyRecord",
    "Evidence",
    "ReporterIdentity",
    "LegalIntake",
    "ModerationAppeal",
    "ModerationFlag",
    "Correction",
    "Publication",
    "PublicationReview",
    "PublicRequest",
    "RightOfResponse",
    "SocialDraft",
    "DepartmentConfig",
    "EmergencyContact",
    "SiteSetting",
    "AgentPresence",
    "SupportConversation",
    "SupportMessage",
    "User",
]
