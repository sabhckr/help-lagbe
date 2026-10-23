# Help Lagbe? — delivery report (22 October 2026)

> **Update, 23 October 2026:** the public site, report flow, categories and public statuses were redesigned. See [REDESIGN-AUDIT.md](REDESIGN-AUDIT.md) for what changed and the current test results. Sections 1–9 below describe the 22 October build.

Status: **a working, tested prototype of the new architecture. Not ready for public launch.** Launch needs the reviews, staffing and external services listed in section 8. Nothing here is a claim of legal compliance or production readiness.

## 1. The original repository

Commit `c89e428` held a 771-line Flask prototype (6 commits, written by a previous AI pass). It had two passing smoke tests, no migrations, CSRF protection, authorization on case data, or MFA, and a single-click editorial publish. Full findings with evidence are in [AUDIT.md](AUDIT.md). The most serious were:

- Any staff role could open and change any case (confirmed by a live request).
- An open redirect on login (confirmed).
- Narrative text leaking onto the public home page.
- No CSRF protection on any form.
- Default secret key and a debug server bound to all interfaces.

The Flask stack was kept. Models, authorization, routes, templates, configuration and tests were rebuilt.

## 2. What changed

| Area | Modules |
|---|---|
| Configuration | `config.py` (development, testing, production; production refuses placeholder secrets), `.env.example`, `wsgi.py`, `gunicorn.conf.py` |
| Authorization | `app/permissions.py` (roles, departments, permission matrix), `app/services/access.py` (need-to-know rules) |
| Data | `app/models/` — 28 tables: cases and history, identities (encrypted and separate), evidence and custody, publication and corrections, support, moderation, audit, settings, legal intake |
| Business rules | `app/services/` — cases, identity (reason-gated unlock), uploads, redaction scanner, publication gates, support, security, audit |
| Public site | 17 pages (Home, Get Help, Report Wrongdoing, Track My Case, Public Awareness, Investigations and Accountability, Legal Help, Digital Safety, Live Human Support, About, Safeguarding, Privacy, Editorial Policy, Corrections, Complaints, Accessibility, Contact), plus reporting, tracking, visitor chat, public requests |
| Staff workspaces | Overview, cases, support desk, publications, public requests, moderation, administration (staff, availability, helplines, policy, health, audit, retention, permissions) |
| Localisation | `app/translations/{en,bn}/` — 1,102 keys in each language, switcher in the header |
| Design | `app/static/css/app.css` — charcoal and ivory tokens, dark mode, reduced-motion, Bengali font stack; `app.js` is progressive only |
| Migrations | `migrations/versions/38dfa181b5f7_initial_schema.py` |
| Tests | `tests/` — 97 tests across auth, authorization, reporting, uploads, cases, publication, support, moderation, admin and platform concerns |
| Docs | `README.md`, `docs/AUDIT.md`, `docs/SECURITY.md`, `docs/PERMISSIONS.md` (generated from code), this report |

The original routes `/submit`, `/login`, `/register`, `/logout`, `/dashboard`, `/editorial` and `/logs` redirect to their new homes. The old `/case/<id>` URL no longer exists. The original SQLite data is not migrated: it held only fictional demo rows.

## 3. Completed and tested versus incomplete

**Built and exercised by automated tests:**

- Anonymous reporting with a one-time key, and confidential reporting with identity stored encrypted apart from the narrative.
- Tracking by reference and key, with no account and no identity shown.
- Email and password sign-in, lockout, staff TOTP MFA (enrolment forced), password policy, safe redirects, CSRF, security headers and no-store caching on private pages.
- Need-to-know case access, reason-gated identity unlock, administrator break-glass, and an audit trail of each of these.
- Evidence upload checked by file signature, hashed, stored outside the web root, with custody records and reason-gated download.
- Severity levels 1 to 4 with written reasoning, escalation and de-escalation history, and overrides. Case lifecycle transitions enforced.
- Outcomes that need confirmation references and second-person verification. Referrals that need consent and a confirmation reference.
- Publication gates: consent, safety, source assessment with a conflict check and right of response, redaction with an identifier scanner, editorial review by a second person, legal review, publish. Child-safety cases cannot become stories.
- Corrections, right of response, withdrawal, and social-media drafts that require approval and a live URL before being marked posted. Nothing posts automatically.
- Live human support: presence, queue, accept, private replies, escalation, follow-up with consent, safe exit, supervisor reads with a logged reason.
- Moderation flags, holds, and appeals decided by a different moderator.
- Administration: staff creation and roles, MFA reset with a reason, departments that cannot be marked staffed without active staff, helplines hidden until a named person verifies them.

**Checked by hand in a browser (desktop and phone width):** report submission and receipt, tracking, staff MFA enrolment, severity assessment, support desk accept and reply, visitor receiving the reply, and language switching. At phone width, three overflow bugs were found and fixed; the home, report, case, support and investigations pages now fit 375 px.

**Rendered without server errors:** every public page in English and Bengali, and about 20 staff pages for each of nine roles (including case and publication detail pages), with zero 5xx responses.

**Not built or not verified:**

- Malware scanning: the ClamAV socket integration exists but was not run against a real daemon. Without it, uploads are marked "not scanned", which is shown to staff.
- Outbound email or SMS: none. Reporters can be reached only through the tracking page.
- Automated retention deletion: only a review list and a manual identity purge.
- Live platform posting: none. Social posts are exported for a person to publish.
- Action and Response workspace: a thin role. It works through assignment, referrals and outcomes, with no dedicated queue and no automatic routing.
- Account-security tooling for cybersecurity staff: guidance pages only.
- Deadline reminders for legal matters: deadlines are stored but do not notify anyone.
- Screen-reader testing, a real-device test, and a low-end Android performance test: not done.
- PostgreSQL and Redis: the code supports them, but only SQLite and in-memory rate limits were tested.

## 4. Local setup

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
flask --app run.py db upgrade
python run.py
```

In development the app also applies migrations on start and seeds fictional accounts. The demo password is `demo-password-2026` and is for local use only. Staff must enrol an authenticator app at first sign-in.

## 5. Environment variables

The full list with comments is in `.env.example`. The required production values are `APP_ENV=production`, `SECRET_KEY` (at least 32 random characters), `IDENTITY_ENCRYPTION_KEY` (a Fernet key), `DATABASE_URL`, `RATELIMIT_STORAGE_URI` (for example Redis), and `SESSION_COOKIE_SECURE=true`. Optional: `CLAMD_SOCKET`, `TRUSTED_PROXY_COUNT`, `EVIDENCE_DIR`.

## 6. Role matrix and key decisions

The full matrix, generated from code, is in [PERMISSIONS.md](PERMISSIONS.md). The decisions that matter most:

- **Administrators manage people and policy, not cases.** They cannot read narratives, identities or support chats except through a logged break-glass read with a written reason.
- **Identity** is encrypted separately. Opening it needs an assignment, a permission, and a reason of at least 15 characters. Refused attempts are logged too.
- **Two-person rules** apply to editorial approval, source assessment, outcome verification, social approval and moderation appeals.
- **Publication labels** are reported allegation, corroborated finding, official statement, court-established outcome, or awareness material. The platform never labels anyone guilty on the strength of a report.
- **Availability is truthful.** Live chat is open only when the support desk is marked staffed and an agent has been seen in the last two minutes.
- **No automatic outbound contact.** No family member, employer or alleged perpetrator is ever contacted by the platform.

## 7. Verification results

Run with `scripts/check.sh` on the final code:

| Check | Result |
|---|---|
| ruff (lint and format) | passed |
| mypy (types, 44 files) | passed |
| bandit (security scan) | passed; two intentional test and demo constants marked `nosec` with reasons |
| pip-audit (dependencies) | no known vulnerabilities (python-dotenv pinned to 1.2.2) |
| pytest | 97 passed |
| compile and template load | passed |
| production configuration check | passed with a sample configuration |

Browser checks and the render sweep are described in section 3.

## 8. Remaining risks, staffing and launch blockers

**Blockers before any public launch:**

1. **Bengali review.** The Bengali text was written by the assistant and a drafting agent. It has not been reviewed by a native Bengali editor or a survivor-support specialist, and the wording of safety-critical content must be approved.
2. **Legal review** of the privacy notice, consent wording, safeguarding policy, publication model and the defamation position on allegations. Nothing has been reviewed by a lawyer.
3. **Verified helplines.** The four helpline numbers in the demo data are unverified and are hidden from the public until a named person checks each one. Each must be called or checked against an official source before a named staff member verifies it.
4. **Child-protection protocol** signed off by the safeguarding lead, including who acts on Level 4 reports and how.
5. **Independent security testing** of the running application, plus a review of the dependencies and deployment.
6. **Production infrastructure:** PostgreSQL, Redis, TLS termination, a non-web-served evidence volume, secrets management, backups, and the malware scanner (or an explicit decision to launch without one).
7. **Accessibility and performance testing** with assistive technology and on a low-end Android device.
8. **Data retention policy** approved, and the identity purge and retention review run on a schedule.

**Staffing needed before the support desk can be marked staffed:**

- At least two trained support agents on rota, each with safeguarding training, plus a named safeguarding supervisor on call.
- A qualified lawyer named as reviewer for legal matters. Legal aid referral partners agreed in writing.
- At least two editors, because the two-person rule cannot be met by one person.
- A cyber or digital-forensics responder for account takeover and image-abuse cases.
- An administrator who keeps the availability settings truthful.

**Known product risks:**

- Reporters who lose the one-time key cannot recover their case. This is a deliberate privacy choice and must be explained clearly.
- The redaction scanner is heuristic. It catches obvious identifiers and nothing else; an editor remains responsible for every published word.
- A legitimately assigned worker can still read what they are assigned. Supervision and audit review are organisational controls the platform cannot replace.
- Without outbound notifications, reporters must return to the tracking page to see updates. Some will not return.

## 9. Git state

The work is **uncommitted** on the `main` branch of the local repository, because no commit was requested. `git status` lists the new and changed files. `.claude/launch.json` is a local preview configuration and can be left out of the commit.
