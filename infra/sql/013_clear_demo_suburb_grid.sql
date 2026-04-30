-- Remove hardcoded demo suburb grid and rank history that were seeded by 003_seed_demo.sql.
-- These have fixed IDs starting with 10000000... and 20000000...
-- After this runs, the admin user's grid will be empty until onboarding is completed,
-- which correctly seeds suburbs filtered by the chosen radius.

BEGIN;
SET LOCAL row_security = off;

DELETE FROM rp_rank_history
WHERE suburb_id IN (
    '10000000-0000-7000-8000-000000000001',
    '10000000-0000-7000-8000-000000000002',
    '10000000-0000-7000-8000-000000000003',
    '10000000-0000-7000-8000-000000000004',
    '10000000-0000-7000-8000-000000000005'
);

DELETE FROM rp_suburb_grid
WHERE id IN (
    '10000000-0000-7000-8000-000000000001',
    '10000000-0000-7000-8000-000000000002',
    '10000000-0000-7000-8000-000000000003',
    '10000000-0000-7000-8000-000000000004',
    '10000000-0000-7000-8000-000000000005'
);

COMMIT;
