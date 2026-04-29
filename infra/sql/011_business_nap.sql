-- Store full NAP fields on client profile for citation consistency checks.
ALTER TABLE rp_clients
  ADD COLUMN IF NOT EXISTS business_address text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS business_phone text NOT NULL DEFAULT '';

COMMENT ON COLUMN rp_clients.business_address IS 'Primary business street address for citations/NAP.';
COMMENT ON COLUMN rp_clients.business_phone IS 'Primary business phone for citations/NAP.';
