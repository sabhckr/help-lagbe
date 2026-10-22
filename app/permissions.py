"""Roles, permissions and the permission matrix.

Rules of thumb:
- Admin is governance, not omniscience: admin manages people, policy and audit, and does NOT
  read narratives, identities or support conversations by default. Reading needs break-glass
  with a written reason and is logged.
- Case content is need-to-know: being in the right department gets you the queue; being assigned
  gets you the narrative; unlocking identity needs a reason and is logged.
"""

from __future__ import annotations

from typing import Iterable

# ---- Roles -------------------------------------------------------------------------------
ROLE_REPORTER = "reporter"
ROLE_ADMIN = "admin"
ROLE_LEGAL = "legal"
ROLE_CYBER = "cyber"
ROLE_SUPPORT = "support"
ROLE_SUPERVISOR = "supervisor"
ROLE_EDITORIAL = "editorial"
ROLE_ACTION = "action"
ROLE_MODERATOR = "moderator"

STAFF_ROLES = (
    ROLE_ADMIN,
    ROLE_LEGAL,
    ROLE_CYBER,
    ROLE_SUPPORT,
    ROLE_SUPERVISOR,
    ROLE_EDITORIAL,
    ROLE_ACTION,
    ROLE_MODERATOR,
)
ALL_ROLES = STAFF_ROLES + (ROLE_REPORTER,)
PRIVILEGED_ROLES = STAFF_ROLES  # MFA required

# ---- Departments (workspaces) ---------------------------------------------------------------
DEPT_ADMIN = "administration"
DEPT_LEGAL = "legal"
DEPT_CYBER = "cyber"
DEPT_SUPPORT = "support"
DEPT_EDITORIAL = "editorial"
DEPT_ACTION = "action"
DEPT_MODERATION = "moderation"

DEPARTMENTS = (DEPT_ADMIN, DEPT_LEGAL, DEPT_CYBER, DEPT_SUPPORT, DEPT_EDITORIAL, DEPT_ACTION, DEPT_MODERATION)

ROLE_DEPARTMENT = {
    ROLE_ADMIN: DEPT_ADMIN,
    ROLE_LEGAL: DEPT_LEGAL,
    ROLE_CYBER: DEPT_CYBER,
    ROLE_SUPPORT: DEPT_SUPPORT,
    ROLE_SUPERVISOR: DEPT_SUPPORT,
    ROLE_EDITORIAL: DEPT_EDITORIAL,
    ROLE_ACTION: DEPT_ACTION,
    ROLE_MODERATOR: DEPT_MODERATION,
    ROLE_REPORTER: None,
}

# Which department first sees a case of a given category (human triage can re-route).
CATEGORY_DEPARTMENT = {
    "bullying": DEPT_SUPPORT,
    "eve_teasing": DEPT_SUPPORT,
    "sexual_harassment": DEPT_SUPPORT,
    "child_abuse": DEPT_SUPPORT,
    "domestic_violence": DEPT_SUPPORT,
    "blackmail": DEPT_SUPPORT,
    "threats": DEPT_SUPPORT,
    "exploitation": DEPT_SUPPORT,
    "bribery": DEPT_EDITORIAL,
    "corruption": DEPT_EDITORIAL,
    "cyber_harassment": DEPT_CYBER,
    "account_takeover": DEPT_CYBER,
    "image_abuse": DEPT_CYBER,
    "legal_question": DEPT_LEGAL,
    "other": DEPT_SUPPORT,
}
CATEGORIES = tuple(CATEGORY_DEPARTMENT.keys())

# ---- Permissions ----------------------------------------------------------------------------
# Case
CASE_VIEW_QUEUE = "case.view_queue"  # see department queue (reference, category, status, severity; no narrative)
CASE_VIEW_METADATA_ANY = "case.view_metadata_any"  # oversight list of every case (no narrative)
CASE_VIEW_NARRATIVE = "case.view_narrative"  # read narrative of cases you are assigned to / in triage for your dept
CASE_TRIAGE = "case.triage"  # set initial severity, route, assign
CASE_TRIAGE_ALL = "case.triage_all"  # triage any department's intake (safeguarding lead)
CASE_ASSIGN = "case.assign"
CASE_NOTE = "case.note"
CASE_SEVERITY = "case.severity"
CASE_STATUS = "case.status"
CASE_IDENTITY_UNLOCK = "case.identity_unlock"  # reason-gated, logged
CASE_EVIDENCE_VIEW = "case.evidence_view"  # list evidence of assigned cases
CASE_EVIDENCE_DOWNLOAD = "case.evidence_download"  # logged
CASE_EVIDENCE_EXPORT = "case.evidence_export"  # logged, restricted
CASE_REFERRAL = "case.referral"
CASE_OUTCOME = "case.outcome"
CASE_MESSAGE_REPORTER = "case.message_reporter"  # post an update visible on the tracking page
CASE_BREAK_GLASS = "case.break_glass"  # admin emergency read with reason, logged
CASE_REOPEN = "case.reopen"
CASE_APPEAL_HANDLE = "case.appeal_handle"
# Legal
LEGAL_INTAKE = "legal.intake"
LEGAL_PRIVILEGED_NOTES = "legal.privileged_notes"
# Cyber
CYBER_FORENSICS = "cyber.forensics"
CYBER_CUSTODY = "cyber.custody"
# Support
SUPPORT_CHAT = "support.chat"
SUPPORT_QUEUE = "support.queue"
SUPPORT_ESCALATE = "support.escalate"
SUPPORT_SUPERVISE = "support.supervise"
SUPPORT_PRESENCE = "support.presence"
# Publication
PUB_DRAFT = "publication.draft"
PUB_SAFETY_REVIEW = "publication.safety_review"
PUB_SOURCE_REVIEW = "publication.source_review"
PUB_REDACT = "publication.redact"
PUB_EDITORIAL_APPROVE = "publication.editorial_approve"
PUB_LEGAL_REVIEW = "publication.legal_review"
PUB_PUBLISH = "publication.publish"
PUB_CORRECT = "publication.correct"
PUB_WITHDRAW = "publication.withdraw"
PUB_VIEW_PIPELINE = "publication.view_pipeline"
SOCIAL_DRAFT = "social.draft"
SOCIAL_APPROVE = "social.approve"
SOCIAL_CONFIRM = "social.confirm_posted"
# Action & response
ACTION_REFERRAL = "action.referral"
ACTION_COMPLAINT_TRACK = "action.complaint_track"
# Moderation
MOD_QUEUE = "moderation.queue"
MOD_ACT = "moderation.act"
MOD_APPEALS = "moderation.appeals"
MOD_FLAG = "moderation.flag"  # any staff can raise a flag
# Admin & audit
ADMIN_USERS = "admin.users"
ADMIN_ROLES = "admin.roles"
ADMIN_CONFIG = "admin.config"
ADMIN_HEALTH = "admin.health"
AUDIT_VIEW_ALL = "audit.view_all"
AUDIT_VIEW_DEPT = "audit.view_department"
WORKSPACE = "workspace.access"

ALL_PERMISSIONS = tuple(
    v for k, v in globals().items() if k.isupper() and isinstance(v, str) and "." in v and k not in ("ROLE_DEPARTMENT",)
)

_COMMON_STAFF = {WORKSPACE, CASE_VIEW_QUEUE, CASE_VIEW_NARRATIVE, CASE_NOTE, MOD_FLAG, AUDIT_VIEW_DEPT}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    ROLE_REPORTER: frozenset(),
    ROLE_ADMIN: frozenset(
        {
            WORKSPACE,
            CASE_VIEW_METADATA_ANY,
            CASE_BREAK_GLASS,
            CASE_ASSIGN,
            ADMIN_USERS,
            ADMIN_ROLES,
            ADMIN_CONFIG,
            ADMIN_HEALTH,
            AUDIT_VIEW_ALL,
            MOD_FLAG,
            PUB_VIEW_PIPELINE,
        }
    ),
    ROLE_LEGAL: frozenset(
        _COMMON_STAFF
        | {
            CASE_TRIAGE,
            CASE_ASSIGN,
            CASE_SEVERITY,
            CASE_STATUS,
            CASE_IDENTITY_UNLOCK,
            CASE_EVIDENCE_VIEW,
            CASE_EVIDENCE_DOWNLOAD,
            CASE_EVIDENCE_EXPORT,
            CASE_REFERRAL,
            CASE_OUTCOME,
            CASE_MESSAGE_REPORTER,
            LEGAL_INTAKE,
            LEGAL_PRIVILEGED_NOTES,
            PUB_LEGAL_REVIEW,
            PUB_VIEW_PIPELINE,
            CASE_APPEAL_HANDLE,
        }
    ),
    ROLE_CYBER: frozenset(
        _COMMON_STAFF
        | {
            CASE_TRIAGE,
            CASE_ASSIGN,
            CASE_SEVERITY,
            CASE_STATUS,
            CASE_IDENTITY_UNLOCK,
            CASE_EVIDENCE_VIEW,
            CASE_EVIDENCE_DOWNLOAD,
            CASE_REFERRAL,
            CASE_OUTCOME,
            CASE_MESSAGE_REPORTER,
            CYBER_FORENSICS,
            CYBER_CUSTODY,
        }
    ),
    ROLE_SUPPORT: frozenset(
        _COMMON_STAFF
        | {
            CASE_TRIAGE,
            CASE_SEVERITY,
            CASE_STATUS,
            CASE_IDENTITY_UNLOCK,
            CASE_EVIDENCE_VIEW,
            CASE_REFERRAL,
            CASE_MESSAGE_REPORTER,
            SUPPORT_CHAT,
            SUPPORT_QUEUE,
            SUPPORT_ESCALATE,
            SUPPORT_PRESENCE,
            PUB_SAFETY_REVIEW,
        }
    ),
    ROLE_SUPERVISOR: frozenset(
        _COMMON_STAFF
        | {
            CASE_TRIAGE,
            CASE_TRIAGE_ALL,
            CASE_ASSIGN,
            CASE_SEVERITY,
            CASE_STATUS,
            CASE_IDENTITY_UNLOCK,
            CASE_EVIDENCE_VIEW,
            CASE_EVIDENCE_DOWNLOAD,
            CASE_REFERRAL,
            CASE_OUTCOME,
            CASE_MESSAGE_REPORTER,
            CASE_REOPEN,
            CASE_APPEAL_HANDLE,
            SUPPORT_CHAT,
            SUPPORT_QUEUE,
            SUPPORT_ESCALATE,
            SUPPORT_SUPERVISE,
            SUPPORT_PRESENCE,
            PUB_SAFETY_REVIEW,
        }
    ),
    ROLE_EDITORIAL: frozenset(
        _COMMON_STAFF
        | {
            CASE_TRIAGE,
            CASE_ASSIGN,
            CASE_SEVERITY,
            CASE_STATUS,
            CASE_EVIDENCE_VIEW,
            CASE_OUTCOME,
            CASE_MESSAGE_REPORTER,
            PUB_DRAFT,
            PUB_SOURCE_REVIEW,
            PUB_REDACT,
            PUB_EDITORIAL_APPROVE,
            PUB_PUBLISH,
            PUB_CORRECT,
            PUB_WITHDRAW,
            PUB_VIEW_PIPELINE,
            SOCIAL_DRAFT,
            SOCIAL_APPROVE,
            SOCIAL_CONFIRM,
        }
    ),
    ROLE_ACTION: frozenset(
        _COMMON_STAFF
        | {
            CASE_TRIAGE,
            CASE_ASSIGN,
            CASE_STATUS,
            CASE_IDENTITY_UNLOCK,
            CASE_EVIDENCE_VIEW,
            CASE_REFERRAL,
            CASE_OUTCOME,
            CASE_MESSAGE_REPORTER,
            ACTION_REFERRAL,
            ACTION_COMPLAINT_TRACK,
        }
    ),
    ROLE_MODERATOR: frozenset(
        _COMMON_STAFF
        | {
            CASE_STATUS,
            MOD_QUEUE,
            MOD_ACT,
            MOD_APPEALS,
            PUB_WITHDRAW,
            CASE_APPEAL_HANDLE,
        }
    ),
}

# Human-readable matrix rows used by docs and the admin "permission matrix" page.
SENSITIVE_ACTIONS = (
    (CASE_VIEW_NARRATIVE, "Read a case narrative (assigned / own-department triage only)"),
    (CASE_IDENTITY_UNLOCK, "Unlock a reporter's private identity (reason required, logged)"),
    (CASE_EVIDENCE_DOWNLOAD, "Download evidence (logged)"),
    (CASE_EVIDENCE_EXPORT, "Export evidence bundle (restricted, logged)"),
    (CASE_BREAK_GLASS, "Emergency read of any case with written reason (logged, reviewed)"),
    (CASE_SEVERITY, "Set severity level 1–4 with reasoning"),
    (CASE_STATUS, "Move a case through the lifecycle"),
    (PUB_EDITORIAL_APPROVE, "Approve a redacted publication (two-person rule)"),
    (PUB_LEGAL_REVIEW, "Legal sign-off on a publication"),
    (PUB_PUBLISH, "Publish an approved story"),
    (SOCIAL_CONFIRM, "Confirm an external post as published (URL required)"),
    (SUPPORT_CHAT, "Read/answer a private support conversation"),
    (SUPPORT_SUPERVISE, "Read any support conversation (supervision)"),
    (ADMIN_ROLES, "Change staff roles"),
    (AUDIT_VIEW_ALL, "Read the full audit trail"),
)


def permissions_for(role: str | None) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role or "", frozenset())


def role_has(role: str | None, *perms: str) -> bool:
    granted = permissions_for(role)
    return all(p in granted for p in perms)


def role_has_any(role: str | None, perms: Iterable[str]) -> bool:
    granted = permissions_for(role)
    return any(p in granted for p in perms)


def department_for_role(role: str | None) -> str | None:
    return ROLE_DEPARTMENT.get(role or "")


def default_department_for_category(category: str) -> str:
    return CATEGORY_DEPARTMENT.get(category, DEPT_SUPPORT)
