"""PostgreSQL cache for Ahrefs keyword API responses (24-hour TTL)."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

AHREFS_CACHE_TTL_HOURS = 24


async def _recover_session_after_db_error(session: AsyncSession) -> None:
    """PostgreSQL aborts the whole transaction after one failed statement."""
    try:
        await session.rollback()
    except Exception:
        pass


def normalize_keyword(keyword: str) -> str:
    return re.sub(r"\s+", " ", (keyword or "").strip().lower())


def build_cache_key(kind: str, country: str, *parts: str) -> str:
    cc = (country or "au").strip().lower()[:2]
    normalized_parts = [normalize_keyword(p) for p in parts if p and p.strip()]
    body = "|".join(normalized_parts)
    return f"{kind}:{cc}:{body}"


def build_lookup_cache_key(country: str, keywords: list[str]) -> str:
    cc = (country or "au").strip().lower()[:2]
    joined = "|".join(sorted(normalize_keyword(k) for k in keywords if k.strip()))
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:40]
    return f"lookup:{cc}:{digest}"


def build_suburbs_hash(suburbs: list[str]) -> str:
    joined = "|".join(sorted(normalize_keyword(s) for s in suburbs if s.strip()))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:24]


async def get_ahrefs_cache(
    session: AsyncSession,
    cache_key: str,
) -> tuple[dict[str, Any] | None, datetime | None, datetime | None]:
    try:
        row = (
            await session.execute(
                text(
                    """
                    SELECT payload, fetched_at, expires_at
                    FROM rp_ahrefs_keyword_cache
                    WHERE cache_key = :key AND expires_at > now()
                    """
                ),
                {"key": cache_key},
            )
        ).mappings().first()
    except Exception:
        await _recover_session_after_db_error(session)
        return None, None, None

    if not row:
        return None, None, None

    payload = row["payload"]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return None, None, None
    if not isinstance(payload, dict):
        return None, None, None

    fetched = row.get("fetched_at")
    expires = row.get("expires_at")
    return payload, fetched, expires


async def set_ahrefs_cache(
    session: AsyncSession,
    cache_key: str,
    payload: dict[str, Any],
    *,
    client_id: UUID | None = None,
    ttl_hours: int = AHREFS_CACHE_TTL_HOURS,
) -> None:
    now = datetime.now(UTC)
    expires = now + timedelta(hours=max(1, ttl_hours))
    try:
        await session.execute(
            text(
                """
                INSERT INTO rp_ahrefs_keyword_cache
                    (cache_key, client_id, payload, fetched_at, expires_at)
                VALUES
                    (:key, :cid, (CAST(:payload AS text))::jsonb, :fetched, :expires)
                ON CONFLICT (cache_key) DO UPDATE SET
                    client_id   = EXCLUDED.client_id,
                    payload     = EXCLUDED.payload,
                    fetched_at  = EXCLUDED.fetched_at,
                    expires_at  = EXCLUDED.expires_at
                """
            ),
            {
                "key": cache_key,
                "cid": str(client_id) if client_id else None,
                "payload": json.dumps(payload),
                "fetched": now,
                "expires": expires,
            },
        )
        await session.flush()
    except Exception:
        await _recover_session_after_db_error(session)


def cache_timestamps_iso(
    fetched_at: datetime | None,
    expires_at: datetime | None,
) -> tuple[str | None, str | None]:
    def _iso(dt: datetime | None) -> str | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat()

    return _iso(fetched_at), _iso(expires_at)


async def purge_expired_ahrefs_cache(session: AsyncSession) -> int:
    try:
        result = await session.execute(
            text("DELETE FROM rp_ahrefs_keyword_cache WHERE expires_at <= now() RETURNING cache_key"),
        )
        return len(result.all())
    except Exception:
        await _recover_session_after_db_error(session)
        return 0
