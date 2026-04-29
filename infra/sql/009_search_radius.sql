-- Maps scan / onboarding: persist chosen search radius (km from metro CBD).
ALTER TABLE rp_clients
  ADD COLUMN IF NOT EXISTS search_radius_km integer NOT NULL DEFAULT 25;

COMMENT ON COLUMN rp_clients.search_radius_km IS 'Suburb grid + maps scan extent from metro CBD (km).';
