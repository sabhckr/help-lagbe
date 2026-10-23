# Role and permission matrix

Generated from `app/permissions.py` (run `python scripts/gen_permissions_doc.py` after changing it). Permissions are fixed per role in code; there is no per-user permission editing. **Case content is additionally need-to-know**: holding `case.view_narrative` only lets you read cases you are assigned to, cases in your own department that are still in intake (submitted/triage), or, for the safeguarding supervisor, cases of the support department. Administrators never read narratives, identities or support chats except through logged break-glass access.

## Roles

- **admin** — Admin & Governance (department: `administration`)
- **legal** — Law & Legal (department: `legal`)
- **cyber** — Cyber & Forensics (department: `cyber`)
- **support** — Human Support (department: `support`)
- **supervisor** — Safeguarding Supervisor (department: `support`)
- **editorial** — Investigations & Editorial (department: `editorial`)
- **action** — Action & Response (department: `action`)
- **moderator** — Moderation (department: `moderation`)
- **reporter** — public account; no workspace permissions at all.

## Sensitive actions

| Action | admin | legal | cyber | support | supervisor | editorial | action | moderator |
|---|---|---|---|---|---|---|---|---|
| Read a case narrative (assigned / own-department triage only) (`case.view_narrative`) |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Unlock a reporter's private identity (reason required, logged) (`case.identity_unlock`) |  | ✓ | ✓ | ✓ | ✓ |  | ✓ |  |
| Download evidence (logged) (`case.evidence_download`) |  | ✓ | ✓ |  | ✓ |  |  |  |
| Export evidence bundle (restricted, logged) (`case.evidence_export`) |  | ✓ |  |  |  |  |  |  |
| Emergency read of any case with written reason (logged, reviewed) (`case.break_glass`) | ✓ |  |  |  |  |  |  |  |
| Set severity level 1–4 with reasoning (`case.severity`) |  | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |
| Move a case through the lifecycle (`case.status`) |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Approve a redacted publication (two-person rule) (`publication.editorial_approve`) |  |  |  |  |  | ✓ |  |  |
| Legal sign-off on a publication (`publication.legal_review`) |  | ✓ |  |  |  |  |  |  |
| Publish an approved story (`publication.publish`) |  |  |  |  |  | ✓ |  |  |
| Confirm an external post as published (URL required) (`social.confirm_posted`) |  |  |  |  |  | ✓ |  |  |
| Read/answer a private support conversation (`support.chat`) |  |  |  | ✓ | ✓ |  |  |  |
| Read any support conversation (supervision) (`support.supervise`) |  |  |  |  | ✓ |  |  |  |
| Change staff roles (`admin.roles`) | ✓ |  |  |  |  |  |  |  |
| Read the full audit trail (`audit.view_all`) | ✓ |  |  |  |  |  |  |  |

## Full matrix

| Permission | admin | legal | cyber | support | supervisor | editorial | action | moderator |
|---|---|---|---|---|---|---|---|---|
| `action.complaint_track` |  |  |  |  |  |  | ✓ |  |
| `action.referral` |  |  |  |  |  |  | ✓ |  |
| `admin.config` | ✓ |  |  |  |  |  |  |  |
| `admin.health` | ✓ |  |  |  |  |  |  |  |
| `admin.roles` | ✓ |  |  |  |  |  |  |  |
| `admin.users` | ✓ |  |  |  |  |  |  |  |
| `audit.view_all` | ✓ |  |  |  |  |  |  |  |
| `audit.view_department` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `case.appeal_handle` |  | ✓ |  |  | ✓ |  |  | ✓ |
| `case.assign` | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |
| `case.break_glass` | ✓ |  |  |  |  |  |  |  |
| `case.evidence_download` |  | ✓ | ✓ |  | ✓ |  |  |  |
| `case.evidence_export` |  | ✓ |  |  |  |  |  |  |
| `case.evidence_view` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `case.identity_unlock` |  | ✓ | ✓ | ✓ | ✓ |  | ✓ |  |
| `case.message_reporter` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `case.note` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `case.outcome` |  | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |
| `case.referral` |  | ✓ | ✓ | ✓ | ✓ |  | ✓ |  |
| `case.reopen` |  |  |  |  | ✓ |  |  |  |
| `case.severity` |  | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |
| `case.status` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `case.triage` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `case.triage_all` |  |  |  |  | ✓ |  |  |  |
| `case.view_metadata_any` | ✓ |  |  |  |  |  |  |  |
| `case.view_narrative` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `case.view_queue` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `cyber.custody` |  |  | ✓ |  |  |  |  |  |
| `cyber.forensics` |  |  | ✓ |  |  |  |  |  |
| `legal.intake` |  | ✓ |  |  |  |  |  |  |
| `legal.privileged_notes` |  | ✓ |  |  |  |  |  |  |
| `moderation.act` |  |  |  |  |  |  |  | ✓ |
| `moderation.appeals` |  |  |  |  |  |  |  | ✓ |
| `moderation.flag` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `moderation.queue` |  |  |  |  |  |  |  | ✓ |
| `publication.correct` |  |  |  |  |  | ✓ |  |  |
| `publication.draft` |  |  |  |  |  | ✓ |  |  |
| `publication.editorial_approve` |  |  |  |  |  | ✓ |  |  |
| `publication.legal_review` |  | ✓ |  |  |  |  |  |  |
| `publication.publish` |  |  |  |  |  | ✓ |  |  |
| `publication.redact` |  |  |  |  |  | ✓ |  |  |
| `publication.safety_review` |  |  |  | ✓ | ✓ |  |  |  |
| `publication.source_review` |  |  |  |  |  | ✓ |  |  |
| `publication.view_pipeline` | ✓ | ✓ |  |  |  | ✓ |  |  |
| `publication.withdraw` |  |  |  |  |  | ✓ |  | ✓ |
| `social.approve` |  |  |  |  |  | ✓ |  |  |
| `social.confirm_posted` |  |  |  |  |  | ✓ |  |  |
| `social.draft` |  |  |  |  |  | ✓ |  |  |
| `story.moderate` |  |  |  |  | ✓ |  |  | ✓ |
| `support.chat` |  |  |  | ✓ | ✓ |  |  |  |
| `support.escalate` |  |  |  | ✓ | ✓ |  |  |  |
| `support.presence` |  |  |  | ✓ | ✓ |  |  |  |
| `support.queue` |  |  |  | ✓ | ✓ |  |  |  |
| `support.supervise` |  |  |  |  | ✓ |  |  |  |
| `workspace.access` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

## Case routing by category

| Category | First department |
|---|---|
| `harassment` | support |
| `threats_blackmail` | support |
| `stalking` | support |
| `hate_incident` | support |
| `abuse_violence` | support |
| `corruption_exploitation` | editorial |
| `online_harm` | cyber |
| `child_safety` | support |
| `other` | support |
| `not_sure` | support |

## Reason-gated, logged actions

The following always require a written reason and write an `AuditEvent` (actor, role, time, case, reason, hashed IP):

- Unlocking a reporter identity (`identity.unlock`; refused attempts are logged as `identity.unlock_refused`).
- Downloading or exporting evidence (`evidence.download`, `evidence.export`; refusals logged).
- Administrator break-glass reads (`case.break_glass`).
- Supervisor reads of support conversations they are not part of (`support.supervisor_read`).
- Audit-trail export (`audit.export`).
- Identity purge under retention (`identity.purge`).
- Role changes and MFA resets (`admin.role_changed`, `admin.mfa_reset`).
