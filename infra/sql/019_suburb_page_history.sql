-- Suburb landing page generate / publish history (Content Engine).

CREATE TABLE IF NOT EXISTS rp_suburb_page_history (
  id                 uuid PRIMARY KEY,
  client_id          uuid NOT NULL REFERENCES rp_clients(client_id) ON DELETE CASCADE,
  status             text NOT NULL DEFAULT 'generated',
  keyword            text NOT NULL DEFAULT '',
  suburb             text NOT NULL DEFAULT '',
  slug               text NOT NULL DEFAULT '',
  title              text NOT NULL DEFAULT '',
  excerpt            text NOT NULL DEFAULT '',
  content            text NOT NULL DEFAULT '',
  word_count         integer,
  image_photo_ids    jsonb NOT NULL DEFAULT '[]',
  model              text,
  wordpress_page_id  integer,
  wordpress_link     text,
  generated_at       timestamptz NOT NULL DEFAULT now(),
  published_at       timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_suburb_page_history_client_time
  ON rp_suburb_page_history (client_id, created_at DESC);

ALTER TABLE rp_suburb_page_history ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = current_schema()
      AND tablename = 'rp_suburb_page_history'
      AND policyname = 'suburb_page_history_isolation'
  ) THEN
    CREATE POLICY suburb_page_history_isolation ON rp_suburb_page_history
      USING (client_id = current_client_id());
  END IF;
END $$;
