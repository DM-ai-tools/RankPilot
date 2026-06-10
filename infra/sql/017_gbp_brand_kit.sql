-- GBP brand kit: colours, voice, logos for AI image branding
CREATE TABLE IF NOT EXISTS rp_gbp_brand_kit (
  client_id uuid PRIMARY KEY REFERENCES rp_clients(client_id) ON DELETE CASCADE,
  brand_name text NOT NULL DEFAULT '',
  agency_type text NOT NULL DEFAULT '',
  language text NOT NULL DEFAULT 'English',
  brand_voice text NOT NULL DEFAULT '',
  forbidden_words text NOT NULL DEFAULT '',
  primary_color text NOT NULL DEFAULT '#FF5F32',
  secondary_color text NOT NULL DEFAULT '#000000',
  heading_font text NOT NULL DEFAULT '',
  body_font text NOT NULL DEFAULT '',
  logo_on_dark_path text,
  logo_on_light_path text,
  updated_at timestamptz NOT NULL DEFAULT now()
);
