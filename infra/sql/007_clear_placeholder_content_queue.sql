-- Remove legacy seed rows (title only, no draft body). Safe on fresh DB (no-op).
BEGIN;
SET LOCAL row_security = off;
DELETE FROM rp_content_queue
WHERE trim(coalesce(payload->>'body', '')) = '';
COMMIT;
