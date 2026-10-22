# Help Lagbe? (হেল্প লাগবে?)

**Human to Human. People for People. — মানুষের পাশে মানুষ।**

A secular, human-centred public-interest platform for Bangladesh:

- **Get Help** — confidential support from real human agents (live chat only when a trained agent is actually present).
- **Report Wrongdoing** — anonymous or confidential reporting of bullying, eve-teasing, bribery, corruption, harassment, abuse, blackmail, threats and exploitation, with evidence upload, safety screening and explicit consent.
- **Raise Awareness** — responsibly reviewed stories, investigations and educational material, published only after consent, safety, source, redaction, editorial and legal gates.
- **Pursue Accountability** — documented referrals, verified outcomes, legal pathways, corrections, right of response and appeals.

No religious preference, test or propaganda. The platform **does not dispatch emergency services** and never contacts a family member, employer or alleged perpetrator on a reporter's behalf.

## Stack

Python 3.11+ · Flask 3 · SQLAlchemy 2 (typed models) · Alembic migrations · Flask-Login + TOTP MFA · Flask-WTF (CSRF) · Flask-Limiter · Fernet-encrypted identity store · Jinja templates with a hand-written CSS design system (no CDN, no JS framework) · JSON-based English/Bengali i18n.

## Local setup

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # edit if you like; defaults are fine for development
flask --app run.py db upgrade   # applies migrations/ to instance/help_lagbe.db
python run.py                   # http://127.0.0.1:5000
```

On first start in development the app applies migrations automatically and seeds **fictional** demo data when the database is empty (`SEED_DEMO_DATA=true`). Nothing is seeded in production.

### Demo accounts (development only)

All demo accounts use the password `demo-password-2026`. Staff must enrol in two-step verification (any TOTP authenticator app) at first sign-in; the manual key is shown on screen.

| Email | Role |
|---|---|
| admin@helplagbe.local | Administration & Governance |
| supervisor@helplagbe.local | Safeguarding supervisor |
| support@helplagbe.local, support2@helplagbe.local | Human Support & Safeguarding |
| legal@helplagbe.local | Law & Legal |
| cyber@helplagbe.local | Cybersecurity & Digital Forensics |
| editor@helplagbe.local, editor2@helplagbe.local | Investigations & Editorial |
| action@helplagbe.local | Action & Response |
| moderator@helplagbe.local | Moderation |
| user@helplagbe.local | Reporter (public account) |

To try live chat: sign in as `support@…`, open **Support desk → I am available**, then visit **Live Human Support** in a private window.

### Useful commands

```bash
flask --app run.py db migrate -m "describe change"   # after editing models
flask --app run.py db upgrade
flask --app run.py create-staff --email a@b.org --name "Name" --role legal
flask --app run.py housekeeping                        # close abandoned chats, list retention reviews
flask --app run.py check-config                        # validate production settings
scripts/check.sh                                       # lint, types, security, dependency audit, tests, build checks
python -m pytest                                       # tests only
```

## Production

- Run with `gunicorn -c gunicorn.conf.py wsgi:app` behind a TLS-terminating reverse proxy; set `TRUSTED_PROXY_COUNT`.
- Set `APP_ENV=production`, a 32+ character `SECRET_KEY`, an `IDENTITY_ENCRYPTION_KEY` (Fernet), `DATABASE_URL` (PostgreSQL recommended), `RATELIMIT_STORAGE_URI` (Redis) and `SESSION_COOKIE_SECURE=true`. The app refuses to start with placeholder secrets.
- Apply migrations with `flask --app wsgi.py db upgrade` as a deploy step; the app never auto-migrates in production.
- Mount `EVIDENCE_DIR` on storage that is not web-served, and configure `CLAMD_SOCKET` if ClamAV is available (otherwise uploads are honestly marked *not scanned*).
- There is **no outbound email or SMS**: reporters are reached only through the Track My Case page. See `docs/DELIVERY-REPORT.md` for launch blockers and staffing requirements.

## Repository layout

```
app/
  __init__.py        application factory, security headers, error pages, CLI
  permissions.py     roles, departments, permission matrix (source of truth)
  i18n.py            JSON translation loader; translations/{en,bn}/*.json
  crypto.py          Fernet helpers for the identity store
  models/            typed SQLAlchemy models (cases, identity, evidence, publication, support, moderation, audit, settings)
  services/          business rules: access (need-to-know), cases (lifecycle), identity (reason-gated unlock),
                     uploads (validation, hashing, scanning, custody), redaction, publication (gates), support, audit
  routes/            public site, auth (MFA), report, track, visitor support, workspace/* (cases, editorial,
                     support desk, moderation, admin), legacy redirects
  templates/         layouts, macros, public pages (+ bilingual content fragments), workspace pages, error states
  static/            app.css design system, app.js progressive enhancement, sw.js offline shell
migrations/          Alembic
tests/               pytest suite (auth, authz, reporting, uploads, cases, publication, support, moderation, admin, platform)
docs/                AUDIT.md, PERMISSIONS.md, SECURITY.md, DELIVERY-REPORT.md
```
