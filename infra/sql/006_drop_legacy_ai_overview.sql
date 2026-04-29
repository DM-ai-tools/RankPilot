-- SEO-only cleanup: remove legacy AEO / AI Overview table if present (older installs).
DROP TABLE IF EXISTS rp_ai_overview CASCADE;
