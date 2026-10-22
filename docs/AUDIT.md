# Help Lagbe? — Repository audit (22 October 2026)

Scope: the repository as received at commit `c89e428` ("Add dashboard, admin templates, and tests"),
six commits made on 22 October 2026 by a previous AI pass. Facts below were established by reading
every file (771 lines in total) and by booting the app and running the tests in a fresh virtualenv.

## 1. What the repository was

| Area | Finding |
|---|---|
| Stack | Flask 3 + Flask-Login + Flask-SQLAlchemy + Flask-Bcrypt, SQLite file DB, Jinja templates. Tailwind and Alpine loaded from public CDNs. |
| Size | 25 files, 771 lines. 4 route modules, 2 model modules, 12 templates, 1 test file. |
| Dependencies | Five unpinned packages in `requirements.txt`. No lock file. No dev tooling (lint, types, security scan). |
| Database | `db.create_all()` at boot, no migrations. Auto-seeds six demo accounts with passwords printed in the README and on the login page. |
| Configuration | One hard-coded config block; `SECRET_KEY` falls back to `dev-secret-change-in-prod`; `run.py` runs `debug=True` on `0.0.0.0`. No dev/prod separation, no `.env.example`. |
| Tests | Two smoke tests (GET `/` and GET `/submit`). Both pass. The test fixture creates and seeds the real on-disk SQLite file before overriding the database URI, so tests touch the dev database. |
| Localization | A "বাংলা / English" button only rewrites `?lang=` and `<html lang>`. There are no translated strings anywhere. |
| UI | Generic Tailwind prototype. No empty, loading, error, offline or permission-denied states beyond Flask's default 403/404 pages. |

## 2. Functional vs. mocked vs. missing (as received)

Genuinely functional:
- Password login/logout/registration (bcrypt hashing).
- Submitting a "complaint" with title, description, category and an anonymous checkbox.
- Staff adding a free-text action that can also change status and severity.
- Editor marking a case published with a typed public summary; a public page per published case.
- An access-log row written whenever any staff member opens a non-anonymous case.

Merely visual or misleading:
- The "Restricted: complainant identity available to authorized personnel" box: no identity is ever shown, yet the view is logged as `view_identity`.
- The language switcher.
- Social-media "draft" page: a template string, no channel, no approval, no export.
- Staff dashboard link "New internal note / or direct to public submit" points at the public form.

Missing entirely: case tracking for anonymous reporters, evidence upload, consent, safety screening, contact preferences, severity reasoning, case lifecycle, outcomes, publication gates, corrections/appeals, live support, moderation, admin user management, audit filters, MFA, rate limiting, CSRF, migrations, i18n, accessibility work, public policy pages.

## 3. Risk-ranked findings

Severity scale: **Critical** = exploitable now with real harm to a reporter; **High** = security or integrity gap that must close before any staff use; **Medium** = correctness/quality; **Low** = hygiene.

| # | Sev. | Finding | Evidence |
|---|---|---|---|
| 1 | Critical | **No CSRF protection** on any form (login, report, action, publication approval). A hostile page can publish a case or change its status on behalf of a logged-in editor. | No token in any template; no `CSRFProtect`. |
| 2 | Critical | **Need-to-know is not enforced.** Every non-`user` role can open every case, record actions, and set any severity or status. `has_role()` also returns true for `admin` on any check. | Logged in as `support`, GET `/case/1` and `/case/2` → 200; POST `/case/1/action` with `status=resolved&severity=critical&notes=x` → 302 accepted. |
| 3 | Critical | **Narrative leaks to the public home page.** `index.html` prints `c.description[:120]` when `public_summary` is empty; `public.html` prints the un-redacted title. Approval does not require a summary to differ from the narrative. | `app/templates/index.html` line 23. |
| 4 | Critical | **Open redirect on login.** The `next` parameter is used unchecked. | POST `/login?next=https://evil.example` → 302 to `https://evil.example`. |
| 5 | High | **No security headers, no cookie hardening.** No CSP, HSTS, X-Frame-Options, Referrer-Policy; `SESSION_COOKIE_SECURE` unset; third-party CDN scripts without SRI. | Response headers of `/` contain none of these. |
| 6 | High | **No rate limiting, lockout or MFA** on login or registration; **no password policy**; sequential integer case IDs allow enumeration. | `routes/auth.py`, `routes/complaints.py`. |
| 7 | High | **Identity is not separated.** `complainant_id` sits on the case row; nothing is encrypted; the access log records no reason and is never written for exports (there are none). | `models/complaint.py`. |
| 8 | High | **Publication is a single click by one editor.** No consent check, safety review, source assessment, redaction verification, legal review, two-person rule, correction or appeal path. Status jumps to `published`. | `routes/admin.py` `approve_publication`. |
| 9 | High | **Default secret and debug server.** `SECRET_KEY` fallback, `debug=True`, bound to all interfaces; demo credentials rendered on the login page. | `app/__init__.py`, `run.py`, `auth/login.html`. |
| 10 | Medium | **Severity and status are free strings** with no reasoning, no history, no escalation record, no human-review requirement. | `routes/complaints.py` `add_action`. |
| 11 | Medium | **Anonymous reporters cannot track a case.** The public ID is shown once in a flash message; `/case/<int>` requires login and ownership. | `routes/complaints.py`. |
| 12 | Medium | **Test fixture seeds the real database** and covers nothing security-relevant. | `tests/test_basic.py`. |
| 13 | Medium | **Localization is non-functional**; Bengali rendering/fonts not considered. | `base.html`. |
| 14 | Medium | No file upload, consent, safety screening, service availability, or human-support features; the home page implies "identity protected" without the controls to back it. | — |
| 15 | Low | `datetime.utcnow` and `Query.get` deprecations; no migrations; unpinned dependencies. | pytest warnings. |

## 4. Decision

The Flask stack is maintainable and appropriate for a small civic service that must run cheaply, so it is kept.
Everything above the framework layer (configuration, models, authorization, routes, templates, tests) is
rebuilt in place. Existing routes that are worth keeping (`/`, `/login`, `/register`, `/logout`, `/submit`,
`/case/...`, `/public/...`, `/editorial`, `/logs`, `/dashboard`) are preserved as redirects or re-implemented
with the same paths where sensible.

## 5. Implementation checklist (ordered by risk)

- [ ] Configuration split (dev/test/prod), secrets from environment, production refuses default secrets.
- [ ] CSRF on every form, security headers, hardened session cookies, safe-redirect helper.
- [ ] Rate limiting, login lockout, password policy, anti-enumeration messages, TOTP MFA for staff roles.
- [ ] Separate encrypted identity store; reason-gated unlock; sensitive-access audit log.
- [ ] Role and permission matrix in code; case-level need-to-know; admin break-glass with reason.
- [ ] Reporting flow: category, narrative, approximate time, optional location, safe contact preferences, evidence upload, immediate-safety screening, explicit consent, anonymous vs confidential.
- [ ] Case tracking for anonymous reporters (reference + secret).
- [ ] Severity levels 1–4 with reasoning, history, overrides; case lifecycle with transition rules; outcomes vocabulary.
- [ ] Seven role workspaces; configurable, truthful availability.
- [ ] Gated publication pipeline; corrections, right of response, appeals, removal requests; social drafts with manual confirmation.
- [ ] Live human support with real presence, queue, escalation, safe exit, follow-up consent.
- [ ] Moderation queue and appeals.
- [ ] i18n (English + Bengali), language switcher, Bengali font stack, accessibility, reduced motion, offline page.
- [ ] Migrations (Alembic), pinned dependencies, lint/type/security/build scripts.
- [ ] Test suite covering auth, authz, identity leakage, evidence, severity, publication gates, corrections, i18n.
