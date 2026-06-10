-- Shared AU suburb GeoJSON boundaries (hex approximations seeded from au_suburbs.py).
CREATE TABLE IF NOT EXISTS rp_suburb_geo (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  suburb text NOT NULL,
  state text,
  postcode text,
  lat double precision,
  lng double precision,
  geojson_polygon jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (suburb, state, postcode)
);

CREATE INDEX IF NOT EXISTS idx_rp_suburb_geo_lookup
  ON rp_suburb_geo (suburb, state, postcode);
