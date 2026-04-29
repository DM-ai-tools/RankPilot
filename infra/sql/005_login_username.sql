-- Login identifier (not email). Bcrypt hash of "admin123" (passlib).
-- Run after 003_seed_demo.sql (and ideally 004_client_password.sql). Safe to re-run.

ALTER TABLE rp_clients ADD COLUMN IF NOT EXISTS login_username citext;

CREATE UNIQUE INDEX IF NOT EXISTS idx_rp_clients_login_username_unique
  ON rp_clients (login_username)
  WHERE login_username IS NOT NULL;

UPDATE rp_clients
SET
  login_username = 'admin',
  password_hash = '$2b$12$3DloWyxsss2oD/MlDEQiKOtKo2fV1vGgUoS0IpN/ba/ntT37X3jfa'
WHERE client_id = '018f3b2e-7b00-7b00-7b00-000000000001';
