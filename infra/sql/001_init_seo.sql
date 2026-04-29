-- RankPilot SEO — PostgreSQL 16+ core schema (Traffic Radius product brief, April 2026).
-- Seven SEO pillars: Maps rank grid, auto-content queue, GBP, citations, reviews (app layer),
-- organic keyword tracking, monthly reports. No AEO / AI-Overview tables.
-- Apply: cd backend && python scripts/apply_migrations.py
-- UUID v7: application layer (uuid6.uuid7). Brand voice: jsonb; optional pgvector later.

CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE OR REPLACE FUNCTION current_client_id() RETURNS uuid AS $$
  SELECT NULLIF(current_setting('app.client_id', true), '')::uuid;
$$ LANGUAGE sql STABLE;

CREATE TABLE rp_clients (
  client_id uuid PRIMARY KEY,
  email citext NOT NULL,
  business_name text NOT NULL,
  abn text,
  business_url text,
  gbp_location_id text,
  wp_url text,
  tier text NOT NULL DEFAULT 'starter',
  stripe_customer_id text,
  plan text,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rp_suburb_grid (
  id uuid PRIMARY KEY,
  client_id uuid NOT NULL REFERENCES rp_clients(client_id) ON DELETE CASCADE,
  suburb text NOT NULL,
  state text,
  postcode text,
  lat double precision,
  lng double precision,
  population int,
  rank_priority int,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (client_id, suburb, postcode)
);

CREATE TABLE rp_rank_history (
  id uuid PRIMARY KEY,
  client_id uuid NOT NULL REFERENCES rp_clients(client_id) ON DELETE CASCADE,
  suburb_id uuid REFERENCES rp_suburb_grid(id) ON DELETE SET NULL,
  keyword text NOT NULL,
  rank_position int,
  feature_snapshot jsonb,
  checked_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_rank_history_client_time ON rp_rank_history (client_id, checked_at DESC);

CREATE TABLE rp_brand_voice (
  id uuid PRIMARY KEY,
  client_id uuid NOT NULL REFERENCES rp_clients(client_id) ON DELETE CASCADE,
  chunk_id text,
  content_chunk text NOT NULL,
  source_url text,
  embedding jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_brand_voice_client ON rp_brand_voice (client_id);

CREATE TABLE rp_actions (
  id uuid PRIMARY KEY,
  client_id uuid NOT NULL REFERENCES rp_clients(client_id) ON DELETE CASCADE,
  action_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}',
  rollback_payload jsonb,
  target_surface text,
  status text NOT NULL DEFAULT 'pending',
  approval_mode text NOT NULL DEFAULT 'approval_required',
  idempotency_key text NOT NULL,
  applied_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (client_id, idempotency_key)
);

CREATE INDEX idx_actions_client_status ON rp_actions (client_id, status);

CREATE TABLE rp_content_queue (
  id uuid PRIMARY KEY,
  client_id uuid NOT NULL REFERENCES rp_clients(client_id) ON DELETE CASCADE,
  content_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'pending',
  approval_mode text NOT NULL DEFAULT 'approval_required',
  generated_at timestamptz,
  published_at timestamptz,
  target_url text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_content_queue_pending ON rp_content_queue (client_id) WHERE status = 'pending';

ALTER TABLE rp_suburb_grid ENABLE ROW LEVEL SECURITY;
ALTER TABLE rp_rank_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE rp_brand_voice ENABLE ROW LEVEL SECURITY;
ALTER TABLE rp_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE rp_content_queue ENABLE ROW LEVEL SECURITY;

CREATE POLICY suburb_grid_isolation ON rp_suburb_grid
  USING (client_id = current_client_id());
CREATE POLICY rank_history_isolation ON rp_rank_history
  USING (client_id = current_client_id());
CREATE POLICY brand_voice_isolation ON rp_brand_voice
  USING (client_id = current_client_id());
CREATE POLICY actions_isolation ON rp_actions
  USING (client_id = current_client_id());
CREATE POLICY content_queue_isolation ON rp_content_queue
  USING (client_id = current_client_id());

ALTER TABLE rp_clients ENABLE ROW LEVEL SECURITY;
CREATE POLICY clients_self ON rp_clients
  USING (client_id = current_client_id());
