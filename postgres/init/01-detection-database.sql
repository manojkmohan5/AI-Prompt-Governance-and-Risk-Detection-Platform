-- The detection service's own database, beside the backend's (POSTGRES_DB).
-- Postgres runs this once, when the postgres-data volume is first created.
-- For a volume made before the detection service existed, run once:
--   docker compose exec postgres createdb -U governance detection
CREATE DATABASE detection;
