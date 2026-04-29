-- Speed up suburb grid + rank joins (dashboard overview, ranks, opportunities).
CREATE INDEX IF NOT EXISTS idx_rp_suburb_grid_client_id ON rp_suburb_grid (client_id);
