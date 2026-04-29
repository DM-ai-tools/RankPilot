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

INSERT INTO rp_suburb_grid (id, client_id, suburb, state, postcode, lat, lng, population, rank_priority)
VALUES
  ('10000000-0000-7000-8000-000000000001', '018f3b2e-7b00-7b00-7b00-000000000001', 'Melbourne CBD', 'VIC', '3000', -37.8136, 144.9631, 28000, 1),
  ('10000000-0000-7000-8000-000000000002', '018f3b2e-7b00-7b00-7b00-000000000001', 'Footscray', 'VIC', '3011', -37.8000, 144.9000, 91000, 2),
  ('10000000-0000-7000-8000-000000000003', '018f3b2e-7b00-7b00-7b00-000000000001', 'Northcote', 'VIC', '3070', -37.7700, 145.0000, 45000, 3),
  ('10000000-0000-7000-8000-000000000004', '018f3b2e-7b00-7b00-7b00-000000000001', 'Essendon', 'VIC', '3040', -37.7600, 144.9200, 110000, 4),
  ('10000000-0000-7000-8000-000000000005', '018f3b2e-7b00-7b00-7b00-000000000001', 'Williamstown', 'VIC', '3016', -37.8600, 144.8900, 28000, 5);

INSERT INTO rp_rank_history (id, client_id, suburb_id, keyword, rank_position, checked_at)
VALUES
  ('20000000-0000-7000-8000-000000000001', '018f3b2e-7b00-7b00-7b00-000000000001', '10000000-0000-7000-8000-000000000001', 'pest control melbourne', 1, now()),
  ('20000000-0000-7000-8000-000000000002', '018f3b2e-7b00-7b00-7b00-000000000001', '10000000-0000-7000-8000-000000000002', 'pest control melbourne', 15, now()),
  ('20000000-0000-7000-8000-000000000003', '018f3b2e-7b00-7b00-7b00-000000000001', '10000000-0000-7000-8000-000000000003', 'pest control melbourne', 7, now()),
  ('20000000-0000-7000-8000-000000000004', '018f3b2e-7b00-7b00-7b00-000000000001', '10000000-0000-7000-8000-000000000004', 'pest control melbourne', NULL, now()),
  ('20000000-0000-7000-8000-000000000005', '018f3b2e-7b00-7b00-7b00-000000000001', '10000000-0000-7000-8000-000000000005', 'pest control melbourne', 18, now());

-- Content queue: no placeholder rows — use "Generate content" in the app (Claude + DB).

INSERT INTO rp_citations (id, client_id, directory, status, drift_flag, last_checked)
VALUES
  ('50000000-0000-7000-8000-000000000001', '018f3b2e-7b00-7b00-7b00-000000000001', 'TrueLocal', 'synced', false, now()),
  ('50000000-0000-7000-8000-000000000002', '018f3b2e-7b00-7b00-7b00-000000000001', 'Yelp AU', 'pending', true, now() - interval '3 days');

COMMIT;
