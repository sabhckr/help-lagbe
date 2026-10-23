# Deploying Help Lagbe? (checked 23 October 2026)

**Status: do not deploy yet.** The code passes every local check, but one production setting cannot be verified without Vercel account access: where the production database lives. Section 3 gives the smallest action needed from the owner.

## 1. Verified facts

| Fact | How it was verified |
|---|---|
| The live site runs commit `9322729`. | Its `app.css` and `app.js` are byte-identical to that commit. |
| The live site is served by Vercel. | `server: Vercel` and `x-vercel-id` response headers. |
| The live app runs its production profile. | It sends `Strict-Transport-Security: max-age=31536000; includeSubDomains`, which this app sets only in production. |
| The live database holds no development seed data. | The live home page says nothing is published; the seed publishes an article. |
| The repository has no `vercel.json`, `.vercelignore` or `.vercel/` link. | File listing. Vercel finds the Flask app through the top-level `app` in `wsgi.py` ([Vercel Flask docs](https://vercel.com/docs/frameworks/backend/flask)). |
| Vercel Functions accept at most 4.5 MB per request and per response. | [Vercel Functions limits](https://vercel.com/docs/functions/limitations). |
| Production never runs migrations by itself. | `create_app` migrates only in development. |
| All four migrations upgrade, downgrade and re-upgrade cleanly, and match the models. | Run on fresh SQLite and on a local PostgreSQL 17 database (`flask db upgrade`, `downgrade base`, `upgrade`, `check`). |
| Old category values are mapped to the new ones. | An old-format case inserted at the initial revision reads `harassment` after upgrade, on both databases. |
| The full test suite passes on SQLite and on PostgreSQL. | 128 tests each. |

## 2. Not verified (needs account access)

1. **Production `DATABASE_URL`.** Its provider and whether it is durable are unknown. Commit `9322729` installs no PostgreSQL, MySQL or Redis driver, and the live `/healthz` query succeeds. A database that works with only the Python standard library is SQLite. *Inference, not confirmed:* the live site probably uses a SQLite file, and a SQLite file on Vercel is not durable storage for reports.
2. **Production `RATELIMIT_STORAGE_URI`.** The production profile refuses `memory://`, so something else is set; its value is unknown.
3. **How deployments are triggered.** The live site changed after the 22 October push to `main`, which is consistent with Vercel's Git integration, but this was not confirmed. A manual deploy would look the same from outside.
4. **The Alembic revision of the production database**, or whether it was created without Alembic.
5. **The client address seen by the app on Vercel.** Rate limits key on the visitor's address. If the app sees Vercel's proxy address instead, everyone shares one limit, and `TRUSTED_PROXY_COUNT=1` is needed.

## 3. Smallest action needed from the owner

In Vercel, open the help-lagbe project, then **Settings → Environment Variables → Production**, and report only the part of each value before `://` (never the full value):

- `DATABASE_URL`
- `RATELIMIT_STORAGE_URI`

Then open **Settings → Git** and note whether the production branch is `main` with automatic deploys on.

If `DATABASE_URL` starts with `sqlite`, a durable database must be provisioned before real reports are accepted. That needs the owner's authorisation; the code already supports `postgresql+psycopg://` and `redis://`.

## 4. Deployment sequence (once section 3 is resolved)

1. **Back up** the production database.
2. From a trusted machine, with the production variables loaded from Vercel (never written into the repository), check the schema without changing it:

   ```bash
   flask --app wsgi.py db current
   ```

   It should print `38dfa181b5f7`. If it prints nothing but the tables exist, the database was created without Alembic; stop and compare the schema before stamping it.
3. **Migrate**, then confirm the revision:

   ```bash
   flask --app wsgi.py db upgrade
   flask --app wsgi.py db current
   ```

   It should now print `c3cee4c88fb2`. The changes add two tables and two nullable columns, and map old category values to the new ones.
4. **Deploy** the new commit. Deploying before step 3 breaks the report form at its first step, because the drafts table would be missing.
5. **Check** `/healthz`, the home page, `/report/1` and a staff sign-in.

**Rollback:** redeploy the previous build. The migrated schema stays compatible with it. The only visible effect is that staff pages of the old build show new category keys untranslated. Do not downgrade below `c3cee4c88fb2` once evidence is stored; that downgrade refuses to run while encrypted files exist.

## 5. Environment variables (names only)

Required in production: `APP_ENV=production`, `SECRET_KEY`, `IDENTITY_ENCRYPTION_KEY`, `DATABASE_URL`, `RATELIMIT_STORAGE_URI`, `SESSION_COOKIE_SECURE=true`.

Optional: `MAX_UPLOAD_MB` (defaults to 4 on Vercel and 25 elsewhere), `TRUSTED_PROXY_COUNT`, `CLAMD_SOCKET`, `DATA_RETENTION_DAYS_CLOSED_CASES`. `EVIDENCE_DIR` is now only read for evidence uploaded before database storage.

## 6. Known limitations on Vercel

- Uploads are capped at 4 MB per request by default, to stay under Vercel's 4.5 MB limit.
- No malware scanner can run on Vercel, so uploads are honestly marked "not scanned".
- Evidence is stored encrypted in the database. That works on a read-only, multi-instance host, but the database grows with each file.
- There is no scheduler. Expired drafts and receipts are deleted whenever the report form is used, at most once a minute per instance. `flask housekeeping` does the same on demand.
