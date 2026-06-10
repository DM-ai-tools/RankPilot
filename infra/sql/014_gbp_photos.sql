-- RankPilot library photos (upload + Runway / Nano Banana generation)
BEGIN;
SET LOCAL row_security = off;

CREATE TABLE IF NOT EXISTS rp_gbp_photos (
  id uuid PRIMARY KEY,
  client_id uuid NOT NULL REFERENCES rp_clients(client_id) ON DELETE CASCADE,
  source text NOT NULL,
  prompt text,
  storage_path text NOT NULL,
  runway_task_id text,
  slot_label text,
  status text NOT NULL DEFAULT 'ready',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rp_gbp_photos_client ON rp_gbp_photos (client_id, created_at DESC);

ALTER TABLE rp_gbp_photos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS gbp_photos_isolation ON rp_gbp_photos;
CREATE POLICY gbp_photos_isolation ON rp_gbp_photos
  USING (client_id = current_client_id());

COMMIT;
