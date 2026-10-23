-- Help Lagbe? production schema upgrade: 38dfa181b5f7 -> c3cee4c88fb2
--
-- Generated on 23 Oct 2026 with
--   APP_ENV=migrate flask --app wsgi.py db upgrade --sql 38dfa181b5f7:c3cee4c88fb2
-- (Alembic, PostgreSQL dialect, no database connection). The statements are Alembic's, unchanged.
-- Two things were added around them:
--   1. Everything runs inside one DO block, so it all succeeds or nothing changes, however the
--      SQL editor handles BEGIN/COMMIT.
--   2. A check first (the database must be at 38dfa181b5f7) and last (it must end at c3cee4c88fb2).
--      Either check failing undoes the whole block.
-- Safe to paste twice: the second run stops at the first check and changes nothing.
-- The SELECT at the end only reads, and shows the result.

DO $upgrade$
DECLARE
    found_revision text;
BEGIN
    SELECT version_num INTO found_revision FROM alembic_version;
    IF found_revision IS DISTINCT FROM '38dfa181b5f7' THEN
        RAISE EXCEPTION 'Stopped, nothing changed: expected revision 38dfa181b5f7, found %', found_revision;
    END IF;

    -- Running upgrade 38dfa181b5f7 -> ad98f3ba2125 (report drafts)

    CREATE TABLE report_drafts (
        id SERIAL NOT NULL,
        token_hash VARCHAR(64) NOT NULL,
        status VARCHAR(16) NOT NULL,
        payload_enc BYTEA,
        receipt_enc BYTEA,
        case_id INTEGER,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(case_id) REFERENCES cases (id)
    );

    CREATE INDEX ix_report_drafts_expires_at ON report_drafts (expires_at);

    CREATE UNIQUE INDEX ix_report_drafts_token_hash ON report_drafts (token_hash);

    CREATE TABLE report_draft_files (
        id SERIAL NOT NULL,
        draft_id INTEGER NOT NULL,
        stored_name VARCHAR(80) NOT NULL,
        original_name VARCHAR(255) NOT NULL,
        mime_type VARCHAR(100) NOT NULL,
        size_bytes INTEGER NOT NULL,
        sha256 VARCHAR(64) NOT NULL,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(draft_id) REFERENCES report_drafts (id),
        UNIQUE (stored_name)
    );

    CREATE INDEX ix_report_draft_files_draft_id ON report_draft_files (draft_id);

    UPDATE alembic_version SET version_num='ad98f3ba2125' WHERE alembic_version.version_num = '38dfa181b5f7';

    -- Running upgrade ad98f3ba2125 -> f8e40f3bb73c (public category keys)

    UPDATE cases SET category = 'harassment' WHERE category = 'bullying';
    UPDATE cases SET category = 'harassment' WHERE category = 'eve_teasing';
    UPDATE cases SET category = 'harassment' WHERE category = 'sexual_harassment';
    UPDATE cases SET category = 'threats_blackmail' WHERE category = 'blackmail';
    UPDATE cases SET category = 'threats_blackmail' WHERE category = 'threats';
    UPDATE cases SET category = 'abuse_violence' WHERE category = 'domestic_violence';
    UPDATE cases SET category = 'corruption_exploitation' WHERE category = 'bribery';
    UPDATE cases SET category = 'corruption_exploitation' WHERE category = 'corruption';
    UPDATE cases SET category = 'corruption_exploitation' WHERE category = 'exploitation';
    UPDATE cases SET category = 'online_harm' WHERE category = 'cyber_harassment';
    UPDATE cases SET category = 'online_harm' WHERE category = 'account_takeover';
    UPDATE cases SET category = 'online_harm' WHERE category = 'image_abuse';
    UPDATE cases SET category = 'child_safety' WHERE category = 'child_abuse';
    UPDATE cases SET category = 'other' WHERE category = 'legal_question';

    UPDATE alembic_version SET version_num='f8e40f3bb73c' WHERE alembic_version.version_num = 'ad98f3ba2125';

    -- Running upgrade f8e40f3bb73c -> c3cee4c88fb2 (evidence stored encrypted in the database)

    ALTER TABLE evidence ADD COLUMN data_enc BYTEA;

    ALTER TABLE report_draft_files ADD COLUMN data_enc BYTEA;

    UPDATE alembic_version SET version_num='c3cee4c88fb2' WHERE alembic_version.version_num = 'f8e40f3bb73c';

    SELECT version_num INTO found_revision FROM alembic_version;
    IF found_revision IS DISTINCT FROM 'c3cee4c88fb2' THEN
        RAISE EXCEPTION 'Stopped, nothing changed: upgrade ended at % instead of c3cee4c88fb2', found_revision;
    END IF;
END
$upgrade$;

SELECT
    (SELECT version_num FROM alembic_version) AS alembic_revision,
    to_regclass('public.report_drafts') IS NOT NULL AS has_report_drafts,
    to_regclass('public.report_draft_files') IS NOT NULL AS has_report_draft_files,
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'evidence' AND column_name = 'data_enc'
    ) AS evidence_has_data_enc;
