-- ============================================================
-- 008_integrations.sql
-- OAuth + WordPress integration credentials per client tenant.
-- Run ONCE after 007_*.sql.
-- ============================================================

CREATE TABLE IF NOT EXISTS rp_integrations (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id     UUID         NOT NULL REFERENCES rp_clients(client_id) ON DELETE CASCADE,
    -- 'gsc' | 'gbp' | 'ga4' | 'wordpress'
    type          TEXT         NOT NULL,
    access_token  TEXT,
    refresh_token TEXT,
    token_expiry  TIMESTAMPTZ,
    -- extra context: for WordPress {site_url, username}; for GA4 {property_id}
    extra_data    JSONB,
    connected_at  TIMESTAMPTZ  DEFAULT now(),
    updated_at    TIMESTAMPTZ  DEFAULT now(),
    UNIQUE (client_id, type)
);

-- Index for quick per-client lookups
CREATE INDEX IF NOT EXISTS idx_rp_integrations_client
    ON rp_integrations (client_id);
