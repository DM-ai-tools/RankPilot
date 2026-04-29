-- Bcrypt hash of "demo123" (passlib default). Used by POST /api/v1/auth/login
ALTER TABLE rp_clients ADD COLUMN IF NOT EXISTS password_hash text;

UPDATE rp_clients
SET password_hash = '$2b$12$QcqGbLfQCwIjLAzS0WminuVrdJgQeo5fIhkahWzAiNrRi83Q0ApXy'
WHERE client_id = '018f3b2e-7b00-7b00-7b00-000000000001';
