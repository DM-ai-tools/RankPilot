-- Migration 012: store scraped NAP per directory so the UI can show
-- the real "wrong value" that was found on each directory listing.
--
-- scraped_nap JSONB shape:
--   { "name": "...", "address": "...", "phone": "...",
--     "name_ok": true/false, "address_ok": true/false, "phone_ok": true/false }
--
-- Apply: cd backend && python scripts/apply_migrations.py

ALTER TABLE rp_citations
  ADD COLUMN IF NOT EXISTS scraped_nap jsonb;
