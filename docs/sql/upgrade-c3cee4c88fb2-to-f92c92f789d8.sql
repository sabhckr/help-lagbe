-- Help Lagbe? production schema upgrade: c3cee4c88fb2 -> f92c92f789d8 (community stories)
--
-- Generated on 23 Oct 2026 with
--   APP_ENV=migrate flask --app wsgi.py db upgrade --sql c3cee4c88fb2:f92c92f789d8
-- (Alembic, PostgreSQL dialect, no database connection). The statements are Alembic's, unchanged
-- apart from indentation. Two things were added around them:
--   1. Everything runs inside one DO block, so it all succeeds or nothing changes, however the
--      SQL editor handles BEGIN/COMMIT.
--   2. A check first (the database must be at c3cee4c88fb2) and last (it must end at f92c92f789d8).
--      Either check failing undoes the whole block.
-- It only adds three empty tables and their indexes; no existing table or row is touched.
-- Safe to paste twice: the second run stops at the first check and changes nothing.
-- The SELECT at the end only reads, and shows the result.

DO $upgrade$
DECLARE
    found_revision text;
BEGIN
    SELECT version_num INTO found_revision FROM alembic_version;
    IF found_revision IS DISTINCT FROM 'c3cee4c88fb2' THEN
        RAISE EXCEPTION 'Stopped, nothing changed: expected revision c3cee4c88fb2, found %', found_revision;
    END IF;

    -- Running upgrade c3cee4c88fb2 -> f92c92f789d8 (community stories)

    CREATE TABLE stories (
        id SERIAL NOT NULL,
        reference VARCHAR(16) NOT NULL,
        manage_hash VARCHAR(64) NOT NULL,
        title VARCHAR(120),
        body TEXT NOT NULL,
        topic VARCHAR(32) NOT NULL,
        display_mode VARCHAR(16) NOT NULL,
        chosen_name VARCHAR(60),
        author_user_id INTEGER,
        support_wanted VARCHAR(16) NOT NULL,
        reply_mode VARCHAR(16) NOT NULL,
        content_warning VARCHAR(24) NOT NULL,
        image_description VARCHAR(300),
        language VARCHAR(5) NOT NULL,
        status VARCHAR(16) NOT NULL,
        review_reason TEXT,
        reviewed_by_id INTEGER,
        reviewed_at TIMESTAMP WITHOUT TIME ZONE,
        published_at TIMESTAMP WITHOUT TIME ZONE,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        hear_you INTEGER NOT NULL,
        not_alone INTEGER NOT NULL,
        thank_you INTEGER NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(author_user_id) REFERENCES users (id),
        FOREIGN KEY(reviewed_by_id) REFERENCES users (id)
    );

    CREATE INDEX ix_stories_published_at ON stories (published_at);

    CREATE UNIQUE INDEX ix_stories_reference ON stories (reference);

    CREATE INDEX ix_stories_status ON stories (status);

    CREATE INDEX ix_stories_topic ON stories (topic);

    CREATE TABLE story_images (
        id SERIAL NOT NULL,
        story_id INTEGER NOT NULL,
        mime_type VARCHAR(32) NOT NULL,
        width INTEGER NOT NULL,
        height INTEGER NOT NULL,
        size_bytes INTEGER NOT NULL,
        sha256 VARCHAR(64) NOT NULL,
        data_enc BYTEA NOT NULL,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(story_id) REFERENCES stories (id)
    );

    CREATE INDEX ix_story_images_story_id ON story_images (story_id);

    CREATE TABLE story_replies (
        id SERIAL NOT NULL,
        story_id INTEGER NOT NULL,
        body TEXT NOT NULL,
        display_name VARCHAR(60),
        status VARCHAR(16) NOT NULL,
        review_reason TEXT,
        reviewed_by_id INTEGER,
        reviewed_at TIMESTAMP WITHOUT TIME ZONE,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(reviewed_by_id) REFERENCES users (id),
        FOREIGN KEY(story_id) REFERENCES stories (id)
    );

    CREATE INDEX ix_story_replies_status ON story_replies (status);

    CREATE INDEX ix_story_replies_story_id ON story_replies (story_id);

    UPDATE alembic_version SET version_num='f92c92f789d8' WHERE alembic_version.version_num = 'c3cee4c88fb2';

    SELECT version_num INTO found_revision FROM alembic_version;
    IF found_revision IS DISTINCT FROM 'f92c92f789d8' THEN
        RAISE EXCEPTION 'Stopped, nothing changed: upgrade ended at % instead of f92c92f789d8', found_revision;
    END IF;
END
$upgrade$;

SELECT
    (SELECT version_num FROM alembic_version) AS alembic_revision,
    to_regclass('public.stories') IS NOT NULL AS has_stories,
    to_regclass('public.story_images') IS NOT NULL AS has_story_images,
    to_regclass('public.story_replies') IS NOT NULL AS has_story_replies;
