-- Ahrefs API response cache (24h TTL) — saves API units on repeated keyword lookups.

CREATE TABLE IF NOT EXISTS rp_ahrefs_keyword_cache (
    cache_key   TEXT PRIMARY KEY,
    client_id   UUID REFERENCES rp_clients(client_id) ON DELETE CASCADE,
    payload     JSONB NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ahrefs_keyword_cache_expires
    ON rp_ahrefs_keyword_cache (expires_at);

CREATE INDEX IF NOT EXISTS idx_ahrefs_keyword_cache_client
    ON rp_ahrefs_keyword_cache (client_id)
    WHERE client_id IS NOT NULL;
