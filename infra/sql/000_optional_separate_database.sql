-- Optional: create a dedicated PostgreSQL database for RankPilot (SEO data layer).
-- Connect as a superuser, then run once:
--
--   psql -U postgres -h localhost -f infra/sql/000_optional_separate_database.sql
--
-- Or: CREATE DATABASE rankpilot; — name must match the database segment in DATABASE_URL
-- (e.g. postgresql+asyncpg://...@localhost:5432/rankpilot). Then run 001→005 migrations.

CREATE DATABASE rankpilot
  WITH OWNER postgres
  ENCODING 'UTF8'
  TEMPLATE template0;
