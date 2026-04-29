-- Run after 001_init_seo.sql (Postgres superuser or role with DDL rights)

ALTER TABLE rp_clients
  ADD COLUMN IF NOT EXISTS primary_keyword text NOT NULL DEFAULT 'pest control melbourne',
  ADD COLUMN IF NOT EXISTS metro_label text NOT NULL DEFAULT 'Melbourne, VIC';

CREATE TABLE IF NOT EXISTS rp_jobs (
  id uuid PRIMARY KEY,
  client_id uuid NOT NULL REFERENCES rp_clients(client_id) ON DELETE CASCADE,
  job_type text NOT NULL,
  status text NOT NULL DEFAULT 'queued',
  payload jsonb NOT NULL DEFAULT '{}',
  result jsonb,
  error_message text,
  idempotency_key text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (client_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_jobs_client_status ON rp_jobs (client_id, status);

ALTER TABLE rp_jobs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS jobs_isolation ON rp_jobs;
CREATE POLICY jobs_isolation ON rp_jobs
  USING (client_id = current_client_id());

CREATE TABLE IF NOT EXISTS rp_citations (
  id uuid PRIMARY KEY,
  client_id uuid NOT NULL REFERENCES rp_clients(client_id) ON DELETE CASCADE,
  directory text NOT NULL,
  status text NOT NULL DEFAULT 'unknown',
  nap_hash text,
  drift_flag boolean NOT NULL DEFAULT false,
  last_checked timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (client_id, directory)
);

CREATE INDEX IF NOT EXISTS idx_citations_client ON rp_citations (client_id);

ALTER TABLE rp_citations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS citations_isolation ON rp_citations;
CREATE POLICY citations_isolation ON rp_citations
  USING (client_id = current_client_id());
