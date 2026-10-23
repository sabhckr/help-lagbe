-- Read-only. Shows the Alembic revision and a fingerprint of every column and index in the public schema.
-- Compare the result with the expected values in docs/PRODUCTION-MIGRATION.md.
SELECT
    (SELECT version_num FROM alembic_version) AS alembic_revision,
    (SELECT count(*) FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE') AS tables,
    (SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public') AS columns,
    (SELECT md5(string_agg(format('%s.%s:%s:%s:%s', table_name, column_name, data_type, is_nullable,
                                  coalesce(character_maximum_length::text, '')),
                           ',' ORDER BY format('%s.%s', table_name, column_name) COLLATE "C"))
        FROM information_schema.columns WHERE table_schema = 'public') AS column_fingerprint,
    (SELECT md5(string_agg(indexname::text, ',' ORDER BY indexname::text COLLATE "C"))
        FROM pg_indexes WHERE schemaname = 'public') AS index_fingerprint;
