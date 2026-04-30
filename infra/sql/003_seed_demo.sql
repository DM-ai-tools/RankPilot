-- Demo tenant + sample data. Run as superuser (RLS bypass).
-- psql "postgresql://rankpilot:rankpilot@localhost:5432/rankpilot" -f infra/sql/003_seed_demo.sql

BEGIN;
SET LOCAL row_security = off;

DELETE FROM rp_clients WHERE client_id = '018f3b2e-7b00-7b00-7b00-000000000001';

INSERT INTO rp_clients (client_id, email, business_name, tier, plan, primary_keyword, metro_label)
VALUES (
  '018f3b2e-7b00-7b00-7b00-000000000001',
  'demo@bugcatchers.test',
  'BugCatchers AU',
  'growth',
  'Growth',
  'pest control melbourne',
  'Melbourne, VIC'
);

-- Suburb grid and rank history intentionally omitted.
-- They are seeded correctly via onboarding (respects user's chosen radius).

-- Content queue: no placeholder rows — use "Generate content" in the app (Claude + DB).

INSERT INTO rp_citations (id, client_id, directory, status, drift_flag, last_checked)
VALUES
  ('50000000-0000-7000-8000-000000000001', '018f3b2e-7b00-7b00-7b00-000000000001', 'TrueLocal', 'synced', false, now()),
  ('50000000-0000-7000-8000-000000000002', '018f3b2e-7b00-7b00-7b00-000000000001', 'Yelp AU', 'pending', true, now() - interval '3 days');

COMMIT;
