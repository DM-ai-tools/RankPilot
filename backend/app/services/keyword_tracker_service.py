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
import contextlib
import logging
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_ahrefs_api_key, get_settings
from app.services.ahrefs_cache_service import build_cache_key, get_ahrefs_cache, set_ahrefs_cache
from app.services.ahrefs_service import AhrefsClient
from app.services.keyword_lookup_service import _country_for_metro

logger = logging.getLogger(__name__)

_MAX_LIVE_CHECKS = 10          # Ahrefs keywords per sync (rest from cache)
_MAX_FORCE_LIVE = 5            # cap live Ahrefs calls on force refresh (avoid 429)
_AHREFS_DELAY_SEC = 2.0        # pause between live Ahrefs keyword checks
_MAX_MAPS_CHECKS = 3           # DataForSEO live Maps checks per sync (published only)
_MAPS_TIMEOUT_SEC = 45.0       # live Maps API can hang — cap wait time
_STALENESS_HOURS = 6           # skip re-check if snapshot < 6h old
_tables_ready = False

_KEYWORD_MAX_WORDS = 8         # keywords longer than this are likely sentences
_KEYWORD_MAX_CHARS = 80        # hard cap on keyword character length
_SENTENCE_PUNCT = re.compile(r"[.!?]{1}")  # sentence-ending punctuation


async def _ensure_tracker_tables() -> None:
    """Create tracker tables if startup bootstrap failed (e.g. old index DDL)."""
    global _tables_ready
    if _tables_ready:
        return
    from app.db.schema_bootstrap import ensure_rp_keyword_tracker_tables

    await ensure_rp_keyword_tracker_tables()
    _tables_ready = True


# ── helpers ──────────────────────────────────────────────────────────────────

def _is_valid_keyword(kw: str) -> bool:
    """Return False for sentence fragments, URLs, or anything too long to be a real keyword."""
    kw = kw.strip()
    if not kw:
        return False
    if len(kw) > _KEYWORD_MAX_CHARS:
        return False
    if len(kw.split()) > _KEYWORD_MAX_WORDS:
        return False
    if _SENTENCE_PUNCT.search(kw):
        return False
    return True


def _normalize_domain(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    return re.sub(r"^www\.", "", urlparse(raw).netloc.lower())


def _domain_matches(url: str, target_domain: str) -> bool:
    if not target_domain:
        return False
    dom = _normalize_domain(url)
    if not dom:
        return False
    return dom == target_domain or dom.endswith(f".{target_domain}") or target_domain in dom


def _name_matches(title: str, business_name: str) -> bool:
    brand = (business_name or "").strip().lower()
    if not brand or len(brand) < 3:
        return False
    return brand in (title or "").strip().lower()


def _client_positions_from_serp(
    rows: list[dict],
    *,
    business_url: str,
    business_name: str,
    page_url: str | None = None,
) -> tuple[int | None, int | None]:
    """Return (organic_position, local_pack_position) for the client's business."""
    target = _normalize_domain(business_url)
    page_path = ""
    if page_url:
        with contextlib.suppress(Exception):
            page_path = urlparse(page_url).path.rstrip("/").lower()
    organic: int | None = None
    local_pack: int | None = None

    for row in rows:
        pos = row.get("position")
        if pos is None:
            continue
        try:
            rank = int(pos)
        except (TypeError, ValueError):
            continue
        kinds = row.get("types") or []
        url = str(row.get("url") or "")
        title = str(row.get("title") or "")
        is_organic = not kinds or "organic" in kinds
        is_local = "local_pack" in kinds

        if is_organic and (
            _domain_matches(url, target)
            or _name_matches(title, business_name)
        ):
            if page_path:
                url_path = urlparse(url).path.rstrip("/").lower() if url else ""
                if page_path in url_path or url_path.endswith(page_path):
                    organic = rank if organic is None else min(organic, rank)
            else:
                organic = rank if organic is None else min(organic, rank)
        if is_local and (
            _name_matches(title, business_name) or _domain_matches(url, target)
        ):
            local_pack = rank if local_pack is None else min(local_pack, rank)

    return organic, local_pack


def _snapshot_is_usable(snap: dict | None) -> bool:
    """True when snapshot has at least one rank or volume value."""
    if not snap:
        return False
    return (
        snap.get("organic_position") is not None
        or snap.get("maps_position") is not None
        or snap.get("search_volume") is not None
    )


async def _upsert_rank_snapshot(
    session: AsyncSession,
    client_id: UUID,
    keyword: str,
    *,
    organic_position: int | None,
    maps_position: int | None,
    search_volume: int | None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO rp_keyword_rank_snapshot
                (client_id, keyword, check_date, checked_at, organic_position, maps_position, search_volume)
            VALUES (:cid, :kw, CURRENT_DATE, now(), :org, :maps, :vol)
            ON CONFLICT (client_id, keyword, check_date)
            DO UPDATE SET
                organic_position = COALESCE(EXCLUDED.organic_position, rp_keyword_rank_snapshot.organic_position),
                maps_position    = COALESCE(EXCLUDED.maps_position, rp_keyword_rank_snapshot.maps_position),
                search_volume    = COALESCE(EXCLUDED.search_volume, rp_keyword_rank_snapshot.search_volume),
                checked_at       = EXCLUDED.checked_at
            """
        ),
        {
            "cid": str(client_id),
            "kw": keyword.lower(),
            "org": organic_position,
            "maps": maps_position,
            "vol": search_volume,
        },
    )
    await session.commit()


async def _get_client_meta(session: AsyncSession, client_id: UUID) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT metro_label, primary_keyword, business_name, business_url,
                       primary_suburb, location_scope
                FROM rp_clients
                WHERE client_id = :cid
                LIMIT 1
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    return dict(row) if row else {}


async def _primary_suburb_point(session: AsyncSession, client_id: UUID, meta: dict) -> dict | None:
    """Best suburb grid point for a live Maps rank check."""
    primary_suburb = str(meta.get("primary_suburb") or "").strip()
    if primary_suburb:
        row = (
            await session.execute(
                text(
                    """
                    SELECT id, suburb, state, postcode, lat, lng
                    FROM rp_suburb_grid
                    WHERE client_id = :cid
                      AND lat IS NOT NULL AND lng IS NOT NULL
                      AND LOWER(suburb) = LOWER(:sub)
                    ORDER BY rank_priority ASC NULLS LAST
                    LIMIT 1
                    """
                ),
                {"cid": str(client_id), "sub": primary_suburb},
            )
        ).mappings().first()
        if row:
            return dict(row)

    row = (
        await session.execute(
            text(
                """
                SELECT id, suburb, state, postcode, lat, lng
                FROM rp_suburb_grid
                WHERE client_id = :cid
                  AND lat IS NOT NULL AND lng IS NOT NULL
                ORDER BY rank_priority ASC NULLS LAST, population DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    return dict(row) if row else None


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


async def _fetch_live_google_organic_rank(
    session: AsyncSession,
    client_id: UUID,
    keyword: str,
    meta: dict,
    *,
    page_url: str | None = None,
) -> int | None:
    """Live Google organic SERP via DataForSEO (suburb-localized when grid exists)."""
    settings = get_settings()
    if not str(settings.dataforseo_login or "").strip() or not str(settings.dataforseo_password or "").strip():
        return None

    business_url = str(meta.get("business_url") or "").strip()
    business_name = str(meta.get("business_name") or "").strip()
    if not business_url and not business_name:
        return None

    suburb = await _primary_suburb_point(session, client_id, meta)
    lat = float(suburb["lat"]) if suburb and suburb.get("lat") is not None else None
    lng = float(suburb["lng"]) if suburb and suburb.get("lng") is not None else None

    from app.services.dataforseo_service import DataForSEOClient

    client = DataForSEOClient(settings)
    try:
        return await asyncio.wait_for(
            client.get_google_organic_rank(
                keyword.strip(),
                business_url,
                page_url=page_url,
                business_name=business_name or None,
                lat=lat,
                lng=lng,
            ),
            timeout=35.0,
        )
    except TimeoutError:
        logger.warning("Live Google organic rank timed out for %r", keyword)
        return None
    except Exception as exc:
        logger.warning("Live Google organic rank failed for %r: %s", keyword, exc)
        return None
    finally:
        await client.aclose()


async def _fetch_ahrefs_ranks(
    session: AsyncSession,
    client_id: UUID,
    keyword: str,
    country: str,
    meta: dict,
    *,
    force: bool = False,
    page_url: str | None = None,
) -> tuple[int | None, int | None, int | None]:
    """(organic_position, search_volume, local_pack_position) for this client's business."""
    cache_key = build_cache_key("tracker-serp-v3", country, str(client_id), keyword)
    cached, _, _ = await get_ahrefs_cache(session, cache_key)
    if isinstance(cached, dict) and not force:
        vol = cached.get("volume")
        if vol is not None or cached.get("organic_position") is not None:
            return (
                cached.get("organic_position"),
                vol,
                cached.get("local_pack_position"),
            )

    if not get_ahrefs_api_key():
        return None, None, None

    business_url = str(meta.get("business_url") or "")
    business_name = str(meta.get("business_name") or "")

    try:
        client = AhrefsClient()
        try:
            # Sequential calls — parallel burst triggers Ahrefs 429 on bulk sync.
            overview = await client.keyword_overview_one(
                keyword, country=country, include_history=False
            )
            positions = await client.serp_overview(
                keyword, country=country, top_positions=20
            )
        finally:
            await client.aclose()

        organic_pos, local_pack_pos = _client_positions_from_serp(
            positions,
            business_url=business_url,
            business_name=business_name,
            page_url=page_url,
        )

        vol = overview.get("volume")
        volume = int(vol) if vol is not None else None

        await set_ahrefs_cache(
            session,
            cache_key,
            {
                "organic_position": organic_pos,
                "volume": volume,
                "local_pack_position": local_pack_pos,
            },
            client_id=client_id,
            ttl_hours=6,
        )
        return organic_pos, volume, local_pack_pos
    except Exception as exc:
        logger.warning("Ahrefs rank/volume fetch failed for %r: %s", keyword, exc)
        if isinstance(cached, dict):
            vol = cached.get("volume")
            if vol is not None or cached.get("organic_position") is not None:
                return (
                    cached.get("organic_position"),
                    vol,
                    cached.get("local_pack_position"),
                )
        return None, None, None


async def _fetch_live_maps_rank(
    session: AsyncSession,
    client_id: UUID,
    keyword: str,
    meta: dict,
) -> int | None:
    """Live Google Maps pack check for client's GBP at primary suburb."""
    settings = get_settings()
    if not str(settings.dataforseo_login or "").strip() or not str(settings.dataforseo_password or "").strip():
        return None

    business_url = str(meta.get("business_url") or "").strip()
    business_name = str(meta.get("business_name") or "").strip()
    if not business_url and not business_name:
        logger.warning("Maps rank check skipped — no business_url or business_name on profile")
        return None

    suburb = await _primary_suburb_point(session, client_id, meta)
    if not suburb:
        logger.warning("Maps rank check skipped — no suburb grid with lat/lng")
        return None

    from app.services.dataforseo_service import DataForSEOClient, format_maps_location_name
    from app.workers.maps_worker import _persist_suburb_rank, _serialize_maps_pack

    location = format_maps_location_name(str(suburb["suburb"]), str(suburb.get("state") or ""))
    client = DataForSEOClient(settings)
    try:
        rank, serp_items = await asyncio.wait_for(
            client.get_maps_rank_with_serp(
                keyword=keyword.strip(),
                location=location,
                business_url=business_url,
                business_name=business_name,
                lat=float(suburb["lat"]),
                lng=float(suburb["lng"]),
            ),
            timeout=_MAPS_TIMEOUT_SEC,
        )
    except TimeoutError:
        logger.warning("Live Maps rank check timed out for %r", keyword)
        return None
    except Exception as exc:
        logger.warning("Live Maps rank check failed for %r: %s", keyword, exc)
        return None
    finally:
        await client.aclose()

    pack = _serialize_maps_pack(serp_items, str(suburb["suburb"]))
    await _persist_suburb_rank(
        str(client_id),
        str(suburb["id"]),
        str(suburb["suburb"]),
        str(suburb.get("state") or "").upper(),
        str(suburb.get("postcode") or ""),
        keyword.strip(),
        rank,
        None,
        pack,
        datetime.now(UTC),
        volume_source="tracker_live",
    )
    return rank


# ── public API ────────────────────────────────────────────────────────────────

async def sync_tracked_keywords(
    session: AsyncSession, client_id: UUID
) -> int:
    """Import keywords from GBP posts, return count of newly added rows."""
    await _ensure_tracker_tables()

    # Purge any previously-imported sentence fragments (bad target_keyword values from old posts)
    await session.execute(
        text(
            """
            DELETE FROM rp_keyword_tracker
            WHERE client_id = :cid
              AND source IN ('gbp_post', 'gbp_post_published')
              AND (
                LENGTH(keyword) > :max_chars
                OR array_length(regexp_split_to_array(trim(keyword), '\\s+'), 1) > :max_words
                OR keyword ~ '[.!?]'
              )
            """
        ),
        {"cid": str(client_id), "max_chars": _KEYWORD_MAX_CHARS, "max_words": _KEYWORD_MAX_WORDS},
    )

    rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT
                  LOWER(TRIM(payload->>'target_keyword')) AS kw,
                  bool_or(status = 'published') AS is_published
                FROM rp_content_queue
                WHERE client_id = :cid
                  AND content_type = 'gbp_post'
                  AND payload->>'target_keyword' IS NOT NULL
                  AND LENGTH(TRIM(payload->>'target_keyword')) > 0
                GROUP BY LOWER(TRIM(payload->>'target_keyword'))
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().all()

    added = 0
    for r in rows:
        kw = str(r["kw"] or "").strip()
        if not kw or not _is_valid_keyword(kw):
            logger.debug("Skipping invalid keyword from post payload: %r", kw)
            continue
        source = "gbp_post_published" if r.get("is_published") else "gbp_post"
        result = await session.execute(
            text(
                """
                INSERT INTO rp_keyword_tracker (client_id, keyword, source)
                VALUES (:cid, :kw, :src)
                ON CONFLICT (client_id, keyword) DO UPDATE
                  SET source = CASE
                    WHEN EXCLUDED.source = 'gbp_post_published' THEN 'gbp_post_published'
                    ELSE rp_keyword_tracker.source
                  END
                """
            ),
            {"cid": str(client_id), "kw": kw, "src": source},
        )
        added += result.rowcount or 0

    suburb_rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT LOWER(TRIM(keyword)) AS kw
                FROM rp_suburb_page_history
                WHERE client_id = :cid
                  AND status = 'published'
                  AND COALESCE(TRIM(keyword), '') <> ''
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().all()

    for r in suburb_rows:
        kw = str(r["kw"] or "").strip()
        if not kw or not _is_valid_keyword(kw):
            continue
        result = await session.execute(
            text(
                """
                INSERT INTO rp_keyword_tracker (client_id, keyword, source)
                VALUES (:cid, :kw, 'suburb_page_published')
                ON CONFLICT (client_id, keyword) DO UPDATE
                  SET source = CASE
                    WHEN EXCLUDED.source = 'suburb_page_published' THEN 'suburb_page_published'
                    WHEN rp_keyword_tracker.source = 'gbp_post_published' THEN 'gbp_post_published'
                    ELSE rp_keyword_tracker.source
                  END
                """
            ),
            {"cid": str(client_id), "kw": kw},
        )
        added += result.rowcount or 0

    await session.commit()
    return added


async def track_published_post_keyword(
    session: AsyncSession, client_id: UUID, keyword: str
) -> None:
    """Add or upgrade a keyword to tracked after a GBP post goes live."""
    kw = keyword.strip().lower()
    if not kw:
        return
    await session.execute(
        text(
            """
            INSERT INTO rp_keyword_tracker (client_id, keyword, source)
            VALUES (:cid, :kw, 'gbp_post_published')
            ON CONFLICT (client_id, keyword) DO UPDATE
              SET source = 'gbp_post_published'
            """
        ),
        {"cid": str(client_id), "kw": kw},
    )
    await session.commit()
    await run_rank_checks(session, client_id, keywords=[kw], force=True)


async def track_published_suburb_page_keyword(
    session: AsyncSession, client_id: UUID, keyword: str
) -> None:
    """Track a suburb landing page keyword after WordPress publish."""
    kw = keyword.strip().lower()
    if not kw or not _is_valid_keyword(kw):
        return
    await session.execute(
        text(
            """
            INSERT INTO rp_keyword_tracker (client_id, keyword, source)
            VALUES (:cid, :kw, 'suburb_page_published')
            ON CONFLICT (client_id, keyword) DO UPDATE
              SET source = CASE
                WHEN EXCLUDED.source = 'suburb_page_published' THEN 'suburb_page_published'
                WHEN rp_keyword_tracker.source = 'gbp_post_published' THEN 'gbp_post_published'
                ELSE rp_keyword_tracker.source
              END
            """
        ),
        {"cid": str(client_id), "kw": kw},
    )
    await session.commit()


def _slug_to_search_keyword(slug: str) -> str:
    return re.sub(r"\s+", " ", (slug or "").replace("-", " ").strip())


def _search_keyword_candidates(keyword: str, slug: str = "") -> list[str]:
    out: list[str] = []
    for raw in [keyword, _slug_to_search_keyword(slug)]:
        k = raw.strip().lower()
        if k and k not in out:
            out.append(k)
    return out


async def check_suburb_page_rank(
    session: AsyncSession,
    client_id: UUID,
    *,
    keyword: str,
    slug: str = "",
    page_url: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Rank check for a published suburb page — Ahrefs SERP + GSC for page URL."""
    from app.services.gsc_service import fetch_gsc_keyword_position

    meta = await _get_client_meta(session, client_id)
    metro = str(meta.get("metro_label") or "")
    country = _country_for_metro(metro) or "au"
    candidates = _search_keyword_candidates(keyword, slug)
    primary_kw = candidates[0] if candidates else keyword.strip().lower()

    best_organic: int | None = None
    best_maps: int | None = None
    volume: int | None = None
    rank_source = "none"

    today = date.today()
    for kw in candidates:
        gsc = await fetch_gsc_keyword_position(
            session,
            client_id,
            keyword=kw,
            page_url=page_url,
            start_date=today - timedelta(days=6),
            end_date=today,
        )
        if gsc and gsc.get("organic_position"):
            gsc_pos = int(gsc["organic_position"])
            best_organic = gsc_pos if best_organic is None else min(best_organic, gsc_pos)
            rank_source = "gsc"

    for kw in candidates:
        organic, vol, maps = await _fetch_ahrefs_ranks(
            session,
            client_id,
            kw,
            country,
            meta,
            force=force,
            page_url=page_url,
        )
        if vol is not None and volume is None:
            volume = vol
        if organic is not None:
            best_organic = organic if best_organic is None else min(best_organic, organic)
            rank_source = "ahrefs" if rank_source == "none" else "gsc+ahrefs"
        if maps is not None:
            best_maps = maps if best_maps is None else min(best_maps, maps)

    maps_pos = await _latest_maps_rank(session, client_id, primary_kw)
    if maps_pos is not None:
        best_maps = maps_pos if best_maps is None else min(best_maps, maps_pos)

    if best_organic is None:
        for kw in candidates:
            live_org = await _fetch_live_google_organic_rank(
                session,
                client_id,
                kw,
                meta,
                page_url=page_url,
            )
            if live_org is not None:
                best_organic = live_org if best_organic is None else min(best_organic, live_org)
                rank_source = "google" if rank_source == "none" else f"{rank_source}+google"

    for snap_kw in candidates:
        await _upsert_rank_snapshot(
            session,
            client_id,
            snap_kw,
            organic_position=best_organic,
            maps_position=best_maps,
            search_volume=volume,
        )

    return {
        "keyword": primary_kw,
        "search_keywords": candidates,
        "organic_position": best_organic,
        "maps_position": best_maps,
        "search_volume": volume,
        "rank_source": rank_source,
        "rank_note": _rank_note(best_organic, best_maps, volume),
    }


async def add_keyword(session: AsyncSession, client_id: UUID, keyword: str) -> bool:
    """Manually add a keyword to track. Returns True if newly added."""
    await _ensure_tracker_tables()
    kw = keyword.strip().lower()
    if not kw or not _is_valid_keyword(kw):
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
    await _ensure_tracker_tables()
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
    await _ensure_tracker_tables()
    meta = await _get_client_meta(session, client_id)
    metro = str(meta.get("metro_label") or "")
    country = _country_for_metro(metro) or "au"

    published_kws: set[str] = set()
    if keywords is None:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT keyword, source
                    FROM rp_keyword_tracker
                    WHERE client_id = :cid
                    ORDER BY
                      CASE source
                        WHEN 'gbp_post_published' THEN 0
                        WHEN 'gbp_post' THEN 1
                        ELSE 2
                      END,
                      added_at DESC
                    """
                ),
                {"cid": str(client_id)},
            )
        ).mappings().all()
        keywords = [str(r["keyword"]) for r in rows]
        published_kws = {
            str(r["keyword"]).lower()
            for r in rows
            if str(r.get("source") or "") in ("gbp_post_published", "suburb_page_published")
        }
    else:
        pub_rows = (
            await session.execute(
                text(
                    """
                    SELECT keyword FROM rp_keyword_tracker
                    WHERE client_id = :cid
                      AND source IN ('gbp_post_published', 'suburb_page_published')
                    """
                ),
                {"cid": str(client_id)},
            )
        ).mappings().all()
        published_kws = {str(r["keyword"]).lower() for r in pub_rows}

    if not keywords:
        return {}

    ahrefs_cap = min(len(keywords), _MAX_FORCE_LIVE if force else _MAX_LIVE_CHECKS)
    maps_cap = _MAX_MAPS_CHECKS
    settings = get_settings()
    ahrefs_ok = bool(get_ahrefs_api_key())
    dataforseo_ok = bool(
        str(settings.dataforseo_login or "").strip()
        and str(settings.dataforseo_password or "").strip()
    )

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
    live_maps_used = 0

    for kw in keywords:
        kw_low = kw.lower()
        maps_pos = await _latest_maps_rank(session, client_id, kw)
        ahrefs_local_pack: int | None = None

        is_published = kw_low in published_kws

        if not force and kw_low in fresh_kws:
            # Already checked today — reuse snapshot only when it has real data
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
            snap_dict = dict(snap) if snap else None
            if _snapshot_is_usable(snap_dict) and not (is_published and snap_dict and snap_dict.get("search_volume") is None):
                results[kw_low] = {
                    "organic_position": snap_dict["organic_position"] if snap_dict else None,
                    "maps_position": maps_pos or (snap_dict.get("maps_position") if snap_dict else None),
                    "search_volume": snap_dict["search_volume"] if snap_dict else None,
                    "from_cache": True,
                    "rank_note": _rank_note(
                        snap_dict.get("organic_position") if snap_dict else None,
                        maps_pos or (snap_dict.get("maps_position") if snap_dict else None),
                        snap_dict.get("search_volume") if snap_dict else None,
                        ahrefs_ok=ahrefs_ok, dataforseo_ok=dataforseo_ok,
                    ),
                }
                continue
        if is_published or live_used < ahrefs_cap:
            organic_pos, volume, ahrefs_local_pack = await _fetch_ahrefs_ranks(
                session, client_id, kw, country, meta, force=force or is_published
            )
            live_used += 1
            if live_used < ahrefs_cap:
                await asyncio.sleep(_AHREFS_DELAY_SEC)
        else:
            # Fallback: pull last snapshot values
            snap = (
                await session.execute(
                    text(
                        """
                        SELECT organic_position, search_volume, maps_position
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
            if maps_pos is None and snap:
                maps_pos = snap.get("maps_position")

        if maps_pos is None and ahrefs_local_pack is not None:
            maps_pos = ahrefs_local_pack

        # Save Ahrefs data immediately so volume appears even if Maps is slow
        await _upsert_rank_snapshot(
            session,
            client_id,
            kw_low,
            organic_position=organic_pos,
            maps_position=maps_pos,
            search_volume=volume,
        )

        # Live Maps is slow — only for published GBP keywords, capped per sync
        if is_published and (force or maps_pos is None) and live_maps_used < maps_cap:
            live_maps = await _fetch_live_maps_rank(session, client_id, kw, meta)
            live_maps_used += 1
            if live_maps is not None:
                maps_pos = live_maps
                await _upsert_rank_snapshot(
                    session,
                    client_id,
                    kw_low,
                    organic_position=organic_pos,
                    maps_position=maps_pos,
                    search_volume=volume,
                )

        results[kw_low] = {
            "organic_position": organic_pos,
            "maps_position": maps_pos,
            "search_volume": volume,
            "from_cache": False,
            "rank_note": _rank_note(organic_pos, maps_pos, volume,
                                    ahrefs_ok=ahrefs_ok, dataforseo_ok=dataforseo_ok),
        }

    return results


def _rank_note(
    organic: int | None, maps: int | None, volume: int | None,
    *, ahrefs_ok: bool = True, dataforseo_ok: bool = True,
) -> str | None:
    if organic is not None or maps is not None:
        return None
    if volume is not None:
        return "Not in top 20 yet — volume tracked; keep posting to improve rank"
    if not ahrefs_ok and not dataforseo_ok:
        return "Rank data unavailable — add AHREFS_API_KEY and DataForSEO credentials in Railway env vars"
    if not ahrefs_ok:
        return "Organic rank unavailable — add AHREFS_API_KEY to Railway env vars"
    if not dataforseo_ok:
        return "Maps rank unavailable — add DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD to Railway env vars"
    return "Rank check complete — keyword not found in top positions yet"


async def _gbp_publish_stats_by_keyword(
    session: AsyncSession, client_id: UUID
) -> dict[str, dict[str, Any]]:
    """Published GBP post count and dates per target_keyword."""
    rows = (
        await session.execute(
            text(
                """
                SELECT
                  LOWER(TRIM(payload->>'target_keyword')) AS kw,
                  COUNT(*) FILTER (WHERE status = 'published')::int AS gbp_post_count,
                  MAX(published_at) FILTER (WHERE status = 'published') AS gbp_last_published_at,
                  MIN(published_at) FILTER (WHERE status = 'published') AS gbp_first_published_at
                FROM rp_content_queue
                WHERE client_id = :cid
                  AND content_type = 'gbp_post'
                  AND payload->>'target_keyword' IS NOT NULL
                  AND LENGTH(TRIM(payload->>'target_keyword')) > 0
                GROUP BY 1
                HAVING COUNT(*) FILTER (WHERE status = 'published') > 0
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().all()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        kw = str(r["kw"] or "").strip()
        if not kw:
            continue
        out[kw] = {
            "gbp_post_count": int(r["gbp_post_count"] or 0),
            "gbp_last_published_at": r["gbp_last_published_at"],
            "gbp_first_published_at": r["gbp_first_published_at"],
        }
    return out


async def get_keyword_tracker_list(
    session: AsyncSession, client_id: UUID
) -> list[dict]:
    """All tracked keywords with latest position + 12-week history sparkline."""
    await _ensure_tracker_tables()
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
                ORDER BY
                  CASE t.source
                    WHEN 'gbp_post_published' THEN 0
                    WHEN 'gbp_post' THEN 1
                    ELSE 2
                  END,
                  t.added_at DESC
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().all()

    publish_stats = await _gbp_publish_stats_by_keyword(session, client_id)

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

        # Position change (latest week vs previous week with data)
        org_change: int | None = None
        maps_change: int | None = None
        weeks_tracked = len(history)
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
        organic_pos = r["organic_position"]
        maps_pos = r["maps_position"]
        volume = r["search_volume"]
        pub = publish_stats.get(kw.lower(), {})
        last_pub = pub.get("gbp_last_published_at")
        first_pub = pub.get("gbp_first_published_at")
        out.append(
            {
                "keyword": kw,
                "source": str(r["source"] or "manual"),
                "added_at": r["added_at"].isoformat() if r["added_at"] else None,
                "organic_position": organic_pos,
                "maps_position": maps_pos,
                "search_volume": volume,
                "organic_change": org_change,
                "maps_change": maps_change,
                "weeks_tracked": weeks_tracked,
                "gbp_post_count": pub.get("gbp_post_count"),
                "gbp_last_published_at": last_pub.isoformat() if last_pub else None,
                "gbp_first_published_at": first_pub.isoformat() if first_pub else None,
                "last_checked": last_checked.isoformat() if last_checked else None,
                "rank_note": _rank_note(organic_pos, maps_pos, volume),
                "history": history,
            }
        )
    return out
