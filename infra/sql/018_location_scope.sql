-- City-wide vs suburb-centered targeting for maps grid + landing pages.
ALTER TABLE rp_clients
  ADD COLUMN IF NOT EXISTS location_scope text NOT NULL DEFAULT 'suburb',
  ADD COLUMN IF NOT EXISTS primary_suburb text NOT NULL DEFAULT '';

COMMENT ON COLUMN rp_clients.location_scope IS 'city = whole metro grid; suburb = radius from primary_suburb';
COMMENT ON COLUMN rp_clients.primary_suburb IS 'Anchor suburb when location_scope = suburb';
