# Production migration: `38dfa181b5f7` → `c3cee4c88fb2`

**Run on 23 October 2026 with the owner's go-ahead, 13:19–13:24 Asia/Dhaka (07:19–07:24 UTC). All five steps passed.**

This runbook upgrades the production database in the Neon console. The database URL never has to leave Neon. The general procedure in [DEPLOYMENT.md](DEPLOYMENT.md) (a hidden prompt plus `flask db upgrade`) does the same job from a terminal.

## Result

| Step | Outcome |
|---|---|
| 1. Pre-flight | Matched the **Before** row exactly. |
| 2. Snapshot | Created "production at 2026-10-23 07:19:47 UTC (manual)". This is the project's one manual snapshot, the Free plan's limit. |
| 3. Probe | Ran as a single query: "Statement executed successfully". |
| 4. Upgrade | The block succeeded in 248 ms. The check row read `c3cee4c88fb2 \| t \| t \| t`. |
| 5. Verify | Matched the **After** row exactly. |

- **How the SQL was entered.** Each query was typed into the editor as a single line: the SQL file with its comment lines removed and its whitespace collapsed. That one-line form was rehearsed locally first, with the same results as the file. Before each run, the editor's text was checked against the rehearsed text by SHA-256.
- **Live site afterwards.** The site still running `9322729` kept working against the upgraded schema: `/healthz` returned `{"status":"ok"}`, and `/` and `/report/new` returned 200.
- **Neon history.** The SQL editor's History list keeps the queries, under titles Neon generated.

## Where production stood before

Production is the Neon project "Help Lagbe", branch `production` (the default and only branch), database `neondb`. A read-only query in the Neon SQL editor on 23 October 2026 found:

- revision `38dfa181b5f7`, the first schema;
- 28 application tables plus `alembic_version`;
- 0 rows in every table: no users, cases, evidence or publications.

The three pending migrations only add things or rename category values:

| Migration | What it does |
|---|---|
| `ad98f3ba2125` | Creates `report_drafts` and `report_draft_files` with their indexes. |
| `f8e40f3bb73c` | Renames old category keys on `cases` with 14 `UPDATE`s. Production has 0 cases, so they change 0 rows. |
| `c3cee4c88fb2` | Adds a nullable `data_enc` column to `evidence` and to `report_draft_files`. |

## Files

- [sql/upgrade-38dfa181b5f7-to-c3cee4c88fb2.sql](sql/upgrade-38dfa181b5f7-to-c3cee4c88fb2.sql) is the exact SQL to run. It holds Alembic's own output for this range, unchanged, inside one `DO` block. A check before and after makes the whole thing all-or-nothing.
- [sql/schema-fingerprint.sql](sql/schema-fingerprint.sql) is a read-only query giving the revision, table and column counts, and fingerprints of every column and index.

## Expected fingerprints

| | Revision | Tables | Columns | Column fingerprint | Index fingerprint |
|---|---|---|---|---|---|
| Before | `38dfa181b5f7` | 29 | 312 | `817d0b5f9dca095fe61bfa5016bef7f7` | `15ac0760aa1e3378c08645f56a156406` |
| After | `c3cee4c88fb2` | 31 | 331 | `41157c6ce3ed9f6da691943016eef62c` | `7b41eb26ff082dd411a6829d18128757` |

Both rows come from local PostgreSQL 17 databases built with this repository's migrations. The table counts include `alembic_version`.

## Steps

Open the Neon console → project "Help Lagbe" → branch `production` → **SQL Editor**, with database `neondb` selected. The editor opens with sample code, including a `CREATE TABLE`. Delete all of it before pasting anything.

1. **Pre-flight (read-only).** Run `schema-fingerprint.sql`. Every value must match the **Before** row. If anything differs, stop: production's schema is not the one the SQL was rehearsed on.
2. **Snapshot.** Go to **Backup & Restore** (turn on **Enhanced view** if the option is hidden) and choose **Create snapshot**. Note the time. The Free plan allows one manual snapshot; if one already exists, decide whether to replace it before going on. Manual snapshots work on root branches only, and `production` is one. ([Neon: backup and restore](https://neon.com/docs/guides/backup-restore))
3. **Editor probe (writes nothing).** Run `DO $probe$ BEGIN PERFORM 1; PERFORM 2; END $probe$;`. It must finish without an error, which shows the editor sends a dollar-quoted block to PostgreSQL in one piece. If it errors, stop and use the terminal route in DEPLOYMENT.md instead.
4. **Upgrade.** Paste the whole of `upgrade-38dfa181b5f7-to-c3cee4c88fb2.sql` and run it once. The last result must be one row: `c3cee4c88fb2 | true | true | true`.
5. **Verify (read-only).** Run `schema-fingerprint.sql` again. Every value must match the **After** row.
6. **Deploy** is a separate decision: push `main`, then do steps 4–5 of DEPLOYMENT.md. Nothing in this runbook deploys.

## If something goes wrong

- **Step 4 shows an error.** Nothing changed: the block undoes itself, and so do the checks. Fix the cause and run it again. A second run after a success stops at the first check ("expected revision 38dfa181b5f7, found c3cee4c88fb2") and changes nothing.
- **To return to the state before the upgrade:** go to **Backup & Restore** → the step 2 snapshot → **Restore** → **One-step restore**. Production keeps its name and connection string, and the state it had before the restore is kept as a branch named "production (old)". The branch ID changes. The database is empty, so nothing is lost.
- **Between the upgrade and the deploy,** the live site (`9322729`) keeps working, because it ignores the new tables and columns. It still writes the old category keys. If a report arrives in that window, rerun the 14 category `UPDATE`s from the SQL file after deploying. `SELECT category, count(*) FROM cases GROUP BY category;` shows whether any old keys remain.

## What was verified, and what was not

The SQL file was rehearsed on throwaway local PostgreSQL 17.11 databases on 23 October 2026, all of them dropped afterwards. Starting from `38dfa181b5f7` with the same 29 tables as production and 0 rows:

- it applied cleanly and ended at `c3cee4c88fb2`;
- `scripts/db_status.py` reported "already at the latest revision";
- `flask db check` found no difference between the schema and the models;
- `pg_dump --schema-only` was identical to an ordinary online `flask db upgrade`;
- a second run stopped at the first check and changed nothing;
- with a conflicting table planted on purpose, it failed partway and left the database exactly as it was (still `38dfa181b5f7`, no new tables or columns).

**Not verified:**

- Whether production's columns and indexes match the rehearsal. Only table names were compared; step 1 checks the rest.
- How Neon's SQL editor handles a `DO` block. Step 3 checks this.
- Production's PostgreSQL version. The SQL uses only long-standing PostgreSQL features.
- The Neon console labels. They come from Neon's documentation as of 23 October 2026.
- That this Neon branch is the database Vercel's `DATABASE_URL` points to. It is the project's only branch, which makes this likely.
