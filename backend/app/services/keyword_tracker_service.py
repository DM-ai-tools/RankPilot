"""GBP keyword rank tracker — monitor weekly positions for posted keywords.

Flow:
1. Auto-imports every target_keyword from rp_content_queue (gbp_post) into rp_keyword_tracker.
2. For each tracked keyword, fetches:
   - Organic Google rank via Ahrefs SERP overview
   - Google Maps rank from the latest rp_rank_history entry
   - Search volume from Ahrefs keyword overview cache
3. Stores a daily snapshot in rp_keyword_rank_snapshot (upsert — one row per keyword per day).
4. Returns keyword list + latest positions + 12-week trend sparkline.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_ahrefs_api_key
from app.services.ahrefs_cache_service import build_cache_key, get_ahrefs_cache, set_ahrefs_cache
from app.services.ahrefs_service import AhrefsClient
from app.services.keyword_lookup_service import _country_for_metro

logger = logging.getLogger(__name__)

_MAX_LIVE_CHECKS = 10          # Ahrefs API calls per sync (rest from cache)
_STALENESS_HOURS = 6           # skip re-check if snapshot < 6h old


# ── helpers ──────────────────────────────────────────────────────────────────

async def _get_client_meta(session: AsyncSession, client_id: UUID) -> dict:
    row = (
        await session.execute(
            text(
                "SELECT metro_label, primary_keyword FROM rp_clients WHERE client_id = :cid LIMIT 1"
            ),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    return dict(row) if row else {}


async def _latest_maps_rank(
    session: AsyncSession, client_id: UUID, keyword: str
) -> int | None:
    """Best (lowest) Maps rank for keyword from the most recent scan snapshot."""
    rows = (
        await session.execute(
            text(
                """
                SELECT rank_position
                FROM rp_rank_history
                WHERE client_id = :cid
                  AND LOWER(TRIM(keyword)) = LOWER(TRIM(:kw))
                  AND rank_position IS NOT NULL
                ORDER BY checked_at DESC
                LIMIT 20
                """
            ),
            {"cid": str(client_id), "kw": keyword},
        )
    ).mappings().all()
    positions = [int(r["rank_position"]) for r in rows if r["rank_position"] is not None]
    return min(positions) if positions else None


async def _organic_rank_and_volume(
    session: AsyncSession,
    client_id: UUID,
    keyword: str,
    country: str,
) -> tuple[int | None, int | None]:
    """(organic_position, search_volume) for keyword via Ahrefs SERP + volume cache."""
    cache_key = build_cache_key("tracker-serp", country, keyword)
    cached, _, _ = await get_ahrefs_cache(session, cache_key)
    if isinstance(cached, dict):
        return cached.get("organic_position"), cached.get("volume")

    if not get_ahrefs_api_key():
        return None, None

    try:
        client = AhrefsClient()
        try:
            positions, overview = await asyncio.gather(
                client.serp_overview(keyword, country=country, top_positions=20),
                client.keyword_overview_one(keyword, country=country, include_history=False),
            )
        finally:
            await client.aclose()

        organic_pos: int | None = None
        for row in positions:
            if row.get("position") is not None:
                organic_pos = int(row["position"])
                break

        vol = overview.get("volume")
        volume = int(vol) if vol is not None else None

        await set_ahrefs_cache(
            session,
            cache_key,
            {"organic_position": organic_pos, "volume": volume},
            client_id=client_id,
            ttl_hours=6,
        )
        return organic_pos, volume
    except Exception as exc:
        logger.warning("Ahrefs rank/volume fetch failed for %r: %s", keyword, exc)
        return None, None


# ── public API ────────────────────────────────────────────────────────────────

async def sync_tracked_keywords(
    session: AsyncSession, client_id: UUID
) -> int:
    """Import keywords from GBP posts, return count of newly added rows."""
    rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT LOWER(TRIM(payload->>'target_keyword')) AS kw
                FROM rp_content_queue
                WHERE client_id = :cid
                  AND content_type = 'gbp_post'
                  AND payload->>'target_keyword' IS NOT NULL
                  AND LENGTH(TRIM(payload->>'target_keyword')) > 0
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().all()

    added = 0
    for r in rows:
        kw = str(r["kw"] or "").strip()
        if not kw:
            continue
        result = await session.execute(
            text(
                """
                INSERT INTO rp_keyword_tracker (client_id, keyword, source)
                VALUES (:cid, :kw, 'gbp_post')
                ON CONFLICT (client_id, keyword) DO NOTHING
                """
            ),
            {"cid": str(client_id), "kw": kw},
        )
        added += result.rowcount or 0

    await session.commit()
    return added


async def add_keyword(session: AsyncSession, client_id: UUID, keyword: str) -> bool:
    """Manually add a keyword to track. Returns True if newly added."""
    kw = keyword.strip().lower()
    if not kw:
        return False
    result = await session.execute(
        text(
            """
            INSERT INTO rp_keyword_tracker (client_id, keyword, source)
            VALUES (:cid, :kw, 'manual')
            ON CONFLICT (client_id, keyword) DO NOTHING
            """
        ),
        {"cid": str(client_id), "kw": kw},
    )
    await session.commit()
    return bool(result.rowcount)


async def remove_keyword(session: AsyncSession, client_id: UUID, keyword: str) -> None:
    kw = keyword.strip().lower()
    await session.execute(
        text(
            "DELETE FROM rp_keyword_tracker WHERE client_id = :cid AND keyword = :kw"
        ),
        {"cid": str(client_id), "kw": kw},
    )
    await session.commit()


async def run_rank_checks(
    session: AsyncSession,
    client_id: UUID,
    *,
    keywords: list[str] | None = None,
    force: bool = False,
) -> dict[str, dict]:
    """Check current ranks for all (or specified) tracked keywords. Returns results dict."""
    meta = await _get_client_meta(session, client_id)
    metro = str(meta.get("metro_label") or "")
    country = _country_for_metro(metro) or "au"

    if keywords is None:
        rows = (
            await session.execute(
                text("SELECT keyword FROM rp_keyword_tracker WHERE client_id = :cid ORDER BY added_at"),
                {"cid": str(client_id)},
            )
        ).mappings().all()
        keywords = [str(r["keyword"]) for r in rows]

    if not keywords:
        return {}

    # Find which already have a fresh snapshot today
    today = datetime.now(UTC).date()
    fresh_rows = (
        await session.execute(
            text(
                """
                SELECT keyword FROM rp_keyword_rank_snapshot
                WHERE client_id = :cid
                  AND DATE(checked_at) = :today
                  AND checked_at > now() - INTERVAL '6 hours'
                """
            ),
            {"cid": str(client_id), "today": today},
        )
    ).mappings().all()
    fresh_kws = {str(r["keyword"]).lower() for r in fresh_rows}

    results: dict[str, dict] = {}
    live_used = 0

    for kw in keywords:
        kw_low = kw.lower()
        maps_pos = await _latest_maps_rank(session, client_id, kw)

        if not force and kw_low in fresh_kws:
            # Already checked today — pull from snapshot
            snap = (
                await session.execute(
                    text(
                        """
                        SELECT organic_position, maps_position, search_volume
                        FROM rp_keyword_rank_snapshot
                        WHERE client_id = :cid AND keyword = :kw
                        ORDER BY checked_at DESC LIMIT 1
                        """
                    ),
                    {"cid": str(client_id), "kw": kw_low},
                )
            ).mappings().first()
            results[kw_low] = {
                "organic_position": snap["organic_position"] if snap else None,
                "maps_position": maps_pos,
                "search_volume": snap["search_volume"] if snap else None,
                "from_cache": True,
            }
            continue

        if live_used < _MAX_LIVE_CHECKS:
            organic_pos, volume = await _organic_rank_and_volume(session, client_id, kw, country)
            live_used += 1
        else:
            # Fallback: pull last snapshot values
            snap = (
                await session.execute(
                    text(
                        """
                        SELECT organic_position, search_volume
                        FROM rp_keyword_rank_snapshot
                        WHERE client_id = :cid AND keyword = :kw
                        ORDER BY checked_at DESC LIMIT 1
                        """
                    ),
                    {"cid": str(client_id), "kw": kw_low},
                )
            ).mappings().first()
            organic_pos = snap["organic_position"] if snap else None
            volume = snap["search_volume"] if snap else None

        # Upsert snapshot (one per day per keyword)
        await session.execute(
            text(
                """
                INSERT INTO rp_keyword_rank_snapshot
                    (client_id, keyword, checked_at, organic_position, maps_position, search_volume)
                VALUES (:cid, :kw, now(), :org, :maps, :vol)
                ON CONFLICT (client_id, keyword, DATE(checked_at))
                DO UPDATE SET
                    organic_position = EXCLUDED.organic_position,
                    maps_position    = EXCLUDED.maps_position,
                    search_volume    = EXCLUDED.search_volume,
                    checked_at       = EXCLUDED.checked_at
                """
            ),
            {
                "cid": str(client_id),
                "kw": kw_low,
                "org": organic_pos,
                "maps": maps_pos,
                "vol": volume,
            },
        )
        await session.commit()
        results[kw_low] = {
            "organic_position": organic_pos,
            "maps_position": maps_pos,
            "search_volume": volume,
            "from_cache": False,
        }

    return results


async def get_keyword_tracker_list(
    session: AsyncSession, client_id: UUID
) -> list[dict]:
    """All tracked keywords with latest position + 12-week history sparkline."""
    rows = (
        await session.execute(
            text(
                """
                SELECT
                  t.keyword,
                  t.source,
                  t.added_at,
                  s.organic_position,
                  s.maps_position,
                  s.search_volume,
                  s.checked_at AS last_checked
                FROM rp_keyword_tracker t
                LEFT JOIN LATERAL (
                  SELECT organic_position, maps_position, search_volume, checked_at
                  FROM rp_keyword_rank_snapshot
                  WHERE client_id = :cid AND keyword = t.keyword
                  ORDER BY checked_at DESC
                  LIMIT 1
                ) s ON true
                WHERE t.client_id = :cid
                ORDER BY t.added_at DESC
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().all()

    out: list[dict] = []
    for r in rows:
        kw = str(r["keyword"])
        # 12-week trend (weekly, most recent first)
        history_rows = (
            await session.execute(
                text(
                    """
                    SELECT
                      DATE_TRUNC('week', checked_at)::date AS week,
                      MIN(organic_position) AS organic_position,
                      MIN(maps_position)    AS maps_position
                    FROM rp_keyword_rank_snapshot
                    WHERE client_id = :cid
                      AND keyword = :kw
                      AND checked_at >= now() - INTERVAL '12 weeks'
                    GROUP BY DATE_TRUNC('week', checked_at)
                    ORDER BY week DESC
                    """
                ),
                {"cid": str(client_id), "kw": kw},
            )
        ).mappings().all()

        history = [
            {
                "week": str(h["week"]),
                "organic_position": h["organic_position"],
                "maps_position": h["maps_position"],
            }
            for h in history_rows
        ]

        # Position change (latest vs previous week)
        org_change: int | None = None
        maps_change: int | None = None
        if len(history) >= 2:
            curr_org = history[0]["organic_position"]
            prev_org = history[1]["organic_position"]
            if curr_org is not None and prev_org is not None:
                org_change = prev_org - curr_org  # positive = improved

            curr_maps = history[0]["maps_position"]
            prev_maps = history[1]["maps_position"]
            if curr_maps is not None and prev_maps is not None:
                maps_change = prev_maps - curr_maps

        last_checked = r["last_checked"]
        out.append(
            {
                "keyword": kw,
                "source": str(r["source"] or "manual"),
                "added_at": r["added_at"].isoformat() if r["added_at"] else None,
                "organic_position": r["organic_position"],
                "maps_position": r["maps_position"],
                "search_volume": r["search_volume"],
                "organic_change": org_change,
                "maps_change": maps_change,
                "last_checked": last_checked.isoformat() if last_checked else None,
                "history": history,
            }
        )
    return out
