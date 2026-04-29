"""Mint a short-lived dev JWT whose `client_id` matches a row in rp_clients."""

import os
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID

from jose import jwt

# Ensure `app` is importable when run from repo root or backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import get_settings  # noqa: E402


def main() -> None:
    settings = get_settings()
    if len(sys.argv) < 2:
        print("Usage: python mint_jwt.py <client_uuid>", file=sys.stderr)
        sys.exit(1)
    client_id = sys.argv[1]
    UUID(client_id)  # validate
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "client_id": client_id,
        "sub": client_id,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    print(token)


if __name__ == "__main__":
    main()
