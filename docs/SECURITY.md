# Security and privacy design

## Principles

1. **Identity is separate and encrypted.** A case row holds no name, phone or email. Confidential reporters' details live in `reporter_identities`, encrypted with Fernet under `IDENTITY_ENCRYPTION_KEY`, and are decrypted only by `services.identity.unlock()`, which requires a permission, an assignment (or admin break-glass) and a written reason, and writes an audit event for every attempt, refused or not.
2. **Need-to-know, enforced server-side.** Templates hide what the server already refuses. Department membership gives a queue (metadata); assignment or own-department triage gives the narrative; reason-gated unlocks give identity and evidence. Administrators manage people and policy and cannot read narratives, identities or support chats without logged break-glass access.
3. **Nothing leaves automatically.** No outbound email/SMS, no auto-publishing, no social posting, no notifications to third parties. Reporters are reached only on the Track My Case page; referrals require recorded consent; a social post is "posted" only when a person enters its live URL.
4. **Truthful availability.** Live chat is open only when the department is marked staffed by an admin and an agent has set themselves available and been seen within two minutes. Helpline numbers are shown only after a named staff member verifies them.
5. **Human judgement on record.** Severity levels, status changes, publication gates, outcomes and moderation decisions all require written reasoning by an identified person; no AI makes decisions anywhere in the system.

## Controls

| Area | Control |
|---|---|
| Authentication | bcrypt passwords (min 12 chars, blocklist, no name/email), lockout after 6 failures for 15 min, generic error messages with equalised bcrypt timing, TOTP MFA mandatory for every staff role (enrolment forced at first sign-in; 5 wrong codes end the attempt), session cleared on login/logout, `session_protection="strong"`, 8-hour staff sessions. |
| CSRF | Flask-WTF token on every form and `X-CSRFToken` header for JSON posts. |
| Headers | CSP (`default-src 'self'`, no inline scripts, `frame-ancestors 'none'`), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, Permissions-Policy, COOP, HSTS in production, `Cache-Control: no-store` on private paths. |
| Cookies | `HttpOnly`, `SameSite=Lax`, `Secure` in production, random cookie names. |
| Redirects | `next`/language redirects validated against the current host (fixes the open redirect found in the audit). |
| Rate limiting | Flask-Limiter on login, MFA, registration, report submission, tracking, requests, chat start and polling. Shared store required in production. |
| Anti-enumeration | Registration and login never reveal whether an email exists; case references are random (40 bits) plus a 70-bit one-time key stored hashed; conversation and request references are random. |
| Uploads | Allow-list of extensions verified by magic bytes, 25 MB request cap, 5 files per report, random storage names under `EVIDENCE_DIR` (never web-served), mode 0600, SHA-256 at receipt, optional ClamAV scan with honest "not scanned" status, quarantine on detection, reason-gated download/export with custody records. |
| Output encoding | Jinja autoescaping everywhere; narratives rendered as text, never as HTML. |
| Database | SQLAlchemy ORM only (parameterised); Alembic migrations; no raw SQL from user input. |
| Logging | Application logs contain IDs and event names only; narratives, identities, message bodies and query strings are never logged (gunicorn access log format excludes query strings, referrers and user agents). |
| Audit | Append-only `audit_events` with actor, role, event, target, case, reason, hashed IP. Sensitive events are highlighted; CSV export is itself logged and contains no identities. |
| Retention | Resolved/closed cases get a retention review date (`DATA_RETENTION_DAYS_CLOSED_CASES`); identities can be purged (logged) while narratives stay for accountability. Abandoned chats close automatically. |
| Secrets | All from environment; production refuses placeholder values; `.env` is git-ignored; `.env.example` has no real secrets. |

## Threat model (summary)

| Threat | Mitigations | Residual risk |
|---|---|---|
| Account takeover of staff | MFA, lockout, strong passwords, session hardening, audit of logins | Phishing of TOTP codes; recommend hardware keys later. |
| Insider misuse | Need-to-know, reason-gated identity/evidence access, break-glass logging, two-person rules on publication/outcomes/appeals, permission matrix review | A legitimately assigned worker can still read what they are assigned; supervision and audit review are organisational controls. |
| Scraping / enumeration | Random references, hashed secrets, rate limits, no public case listing | — |
| Forged or malicious reports | Honeypot, rate limits, moderation flags, severity by humans, "allegation" labelling, no publication without corroboration | Determined human fabrication needs editorial verification. |
| Evidence tampering | SHA-256 at receipt, hash verification, custody records, 0600 files, soft delete only | Host compromise. |
| Doxxing via publication | Consent gate, redaction checklist + automatic identifier scan, two-person editorial rule, legal review, child-safety ban, right of response, withdrawal | Scanner is heuristic; humans remain responsible. |
| Retaliation against reporters | No outbound contact, "do not contact" record, safe hours, quick exit, no-store caching, no identity in logs/exports | A reporter's own device. |
| Denial of service | Rate limits, upload caps, gunicorn limits | Needs infrastructure-level protection. |
| Malware in uploads | Magic-byte check, optional ClamAV, quarantine, downloads are attachments | Without ClamAV, files are unscanned (shown honestly). |

## Known gaps / not claims

- No independent penetration test or legal review has been performed. Nothing here is a claim of legal compliance.
- Secrets at rest depend on the host (`IDENTITY_ENCRYPTION_KEY` must be in a secret store).
- ClamAV, Redis, PostgreSQL and TLS termination are deployment responsibilities.
