-- Module-based local SEO page structure (Content Engine).

ALTER TABLE rp_suburb_page_history
  ADD COLUMN IF NOT EXISTS module_set_used jsonb NOT NULL DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS modules_json jsonb NOT NULL DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS nearby_suburbs text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS service_focus text NOT NULL DEFAULT '';
