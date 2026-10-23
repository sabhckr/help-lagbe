# Deploying Help Lagbe? (checked 23 October 2026)

**Status: the production database was migrated to `c3cee4c88fb2` on 23 October ([PRODUCTION-MIGRATION.md](PRODUCTION-MIGRATION.md)). Deploying `main` is the next step.** Pushing `main` first would break the report form, because the new tables would be missing.

## 1. Facts

| Fact | Source |
|---|---|
| Production `DATABASE_URL` starts with `postgresql`. | Confirmed by the owner from the Vercel dashboard, 23 October. |
| Production's database is Neon project "Help Lagbe", branch `production`, database `neondb`. It was at revision `38dfa181b5f7` with every table empty, and was migrated to `c3cee4c88fb2` on 23 October. | Queries in the Neon SQL editor, 23 October, on the branch the owner named. A snapshot was taken first. |
| The live site runs commit `35a07e6`. Every push to `main` deploys. | Vercel's GitHub commit statuses: "Deployment has completed" for `35a07e6` (22 October, 14:00 UTC) and for each push before it, except `b299e3c`, which failed. `9322729` has no Vercel status. Its static files are identical to `35a07e6`, which misled an earlier check. |
| The live site is served by Vercel and runs the app's production profile. | `server: Vercel`, `x-vercel-id`, and the production-only HSTS header. |
| The live database holds no development seed data. | The live home page shows nothing published. |
| Vercel builds from `api/index.py` (the entry point), `vercel.json` (functions pinned to region `sin1`, next to the Neon database in Singapore), `.python-version` (3.12) and the `[project]` dependency list in `pyproject.toml`. That list must match `requirements.txt`, and a test checks this. | Commits `b299e3c`–`35a07e6`. |
| Templates live in `app/templates/site`, not `public`. | Vercel leaves directories named `public` out of the function bundle (commit `35a07e6`). A test keeps any `app/**/public` directory from coming back. |
| Vercel Functions accept at most 4.5 MB per request and per response. | [Vercel Functions limits](https://vercel.com/docs/functions/limitations). |
| Production never migrates by itself. | `create_app` migrates only in development, and only against a local database. |
| All four migrations upgrade, downgrade and re-upgrade, and match the models. | Run on SQLite and on local PostgreSQL 17, including with `postgres://` and `postgresql://` URLs. |
| The full test suite passes on SQLite and PostgreSQL. | 139 tests. |

An earlier version of this document inferred that production used SQLite, because commit `9322729` installs no PostgreSQL driver. That inference was wrong: commit `b299e3c` added `psycopg` 3 for the live build. The code rewrites any `postgres://`, `postgresql://` or `postgresql+psycopg2://` URL to use that driver.

## 2. Still unverified

1. **That the Neon branch above is what Vercel's `DATABASE_URL` points to.** It is the project's only branch, which makes this likely.
2. **How rate limits are stored.** Production starts only if `RATELIMIT_STORAGE_URI` points at a shared store or `ALLOW_MEMORY_RATELIMIT=true` is set. The live build has the same rule, so whichever one production uses today keeps working. With memory storage, each function instance counts on its own, so limits are looser than configured.
3. **The client address the app sees on Vercel.** If rate limits group everyone under one proxy address, set `TRUSTED_PROXY_COUNT=1`.

## 3. Procedure

Steps 1–3 for the upgrade from `38dfa181b5f7` to `c3cee4c88fb2` were done on 23 October in the Neon SQL editor ([PRODUCTION-MIGRATION.md](PRODUCTION-MIGRATION.md)). The terminal route below is for future migrations.

Run these from a clone of this repository with its virtualenv active. The production URL is typed into a hidden prompt, so it never appears on screen or in shell history.

**Step 1: read-only check.**

```bash
read -rs DATABASE_URL && export DATABASE_URL
python scripts/db_status.py
```

The script prints the driver, the Alembic revision, table and row counts and a verdict. It never prints the URL and never writes. Expected: revision `38dfa181b5f7`, verdict "needs `flask db upgrade`". If it reports tables without Alembic history, stop: the schema must be compared before anything is stamped.

**Step 2: back up.** Take a snapshot or branch of the production database in the provider's dashboard.

**Step 3: migrate.** The `migrate` profile never seeds data, never needs the application secrets, and refuses to run without an explicit `DATABASE_URL`.

```bash
APP_ENV=migrate flask --app wsgi.py db upgrade
python scripts/db_status.py
unset DATABASE_URL
```

Expected verdict: "already at the latest revision" (`c3cee4c88fb2`).

**Step 4: deploy.** Push `main`, or promote the deployment in Vercel. The site that is live now keeps working against the migrated schema in the meantime. The only visible effect there is that its staff pages show new category keys untranslated.

**Step 5: check.** Open `/healthz`, the home page and `/report/1`, and test a staff sign-in.

**Rollback:** redeploy the previous build; the schema can stay. Do not downgrade below `c3cee4c88fb2` once evidence is stored. That downgrade refuses to run while encrypted files exist, and the category mapping in `f8e40f3bb73c` is one-way, so restore from the step 2 backup if the data must go back.

**Staff accounts on production:** create the first admin, or reset a forgotten staff password, from this repository. Each command asks for the database URL and the password without showing them:

```bash
read -rs "DATABASE_URL?Paste DATABASE_URL: " && echo && DATABASE_URL="$DATABASE_URL" APP_ENV=migrate .venv/bin/flask --app wsgi.py create-staff --email you@example.org --name "Your Name" --role admin; unset DATABASE_URL
```

```bash
read -rs "DATABASE_URL?Paste DATABASE_URL: " && echo && DATABASE_URL="$DATABASE_URL" APP_ENV=migrate .venv/bin/flask --app wsgi.py reset-password --email you@example.org --reason "Forgot the password"; unset DATABASE_URL
```

A reset keeps two-step verification and clears any login lockout. It is recorded in the audit trail with the reason, and marked as sensitive. Add `--require-change` when resetting someone else's password, so that they choose their own at next sign-in. A reset does not sign out sessions that are already open.

## 4. Environment variables (names only)

Required in production: `APP_ENV=production`, `SECRET_KEY`, `IDENTITY_ENCRYPTION_KEY`, `DATABASE_URL`, `RATELIMIT_STORAGE_URI`, `SESSION_COOKIE_SECURE=true`.

Optional: `ALLOW_MEMORY_RATELIMIT` (lets production start without a shared rate-limit store), `INSTANCE_PATH` (defaults to `/tmp/help_lagbe_instance` on Vercel), `MAX_UPLOAD_MB` (defaults to 4 on Vercel and 25 elsewhere), `TRUSTED_PROXY_COUNT`, `CLAMD_SOCKET`, `DATA_RETENTION_DAYS_CLOSED_CASES`. `EVIDENCE_DIR` is only read for files uploaded before database storage.

## 5. Behaviour on Vercel

- **Connection pool:** PostgreSQL connections use a small pool on Vercel, recycle after five minutes, and disable server-side prepared statements, so transaction-mode poolers such as PgBouncer, Neon and Supabase work.
- **Uploads:** they are capped at 4 MB per request by default, under Vercel's 4.5 MB limit.
- **Evidence storage:** evidence is stored encrypted in the database, so no writable disk is needed.
- **Scanning:** no malware scanner runs on Vercel, so uploads are honestly marked "not scanned".
- **Clean-up:** there is no scheduler. Expired drafts and receipts are deleted when the report form is used, at most once a minute per instance. `flask housekeeping` does the same on demand.
