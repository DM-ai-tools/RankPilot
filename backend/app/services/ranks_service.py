"""L1/L2: Suburb rank grid for visibility map."""

from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_ahrefs_api_key
from app.lib.primary_keywords import scan_keyword_from_primary
from app.lib.visibility_scoring import count_rank_bands, visibility_score_pct
from app.schemas.ranks import MapPackPlace, SuburbRankRow, SuburbRanksResponse
from app.services.ahrefs_cache_service import (
    build_cache_key,
    build_suburbs_hash,
    get_ahrefs_cache,
    set_ahrefs_cache,
)
from app.services.ahrefs_service import AhrefsClient
from app.services.keyword_lookup_service import _country_for_metro

logger = logging.getLogger(__name__)


def _pins_from_snapshot(snap: object) -> list[MapPackPlace]:
    if not isinstance(snap, dict):
        return []
    raw = snap.get("maps_pack")
    if not isinstance(raw, list):
        return []
    pins: list[MapPackPlace] = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        try:
            la = float(it["lat"])
            lo = float(it["lng"])
        except (KeyError, TypeError, ValueError):
            continue
        title = str(it.get("title") or "").strip() or "Business"
        rnk = it.get("rank")
        try:
            rank_i = int(rnk) if rnk is not None else None
        except (TypeError, ValueError):
            rank_i = None
        dom = it.get("domain")
        url = it.get("url")
        addr = it.get("address")
        sub = it.get("suburb_context")
        pins.append(
            MapPackPlace(
                title=title,
                lat=la,
                lng=lo,
                rank=rank_i,
                pack_rank_best=rank_i,
                pack_rank_worst=rank_i,
                suburb_scan_count=1,
                domain=str(dom).strip()[:160] if dom else None,
                url=str(url).strip()[:400] if url else None,
                address=str(addr).strip()[:240] if addr else None,
                suburb_context=str(sub).strip()[:120] if sub else None,
            )
        )
    return pins


def _competitor_dedupe_key(p: MapPackPlace) -> str:
    dom = (p.domain or "").strip().lower()
    if dom:
        return f"d:{dom}|{round(p.lat, 4)}|{round(p.lng, 4)}"
    return f"t:{p.title.strip().lower()}|{round(p.lat, 4)}|{round(p.lng, 4)}"


def _dedupe_map_competitors(pins: list[MapPackPlace], limit: int = 120) -> list[MapPackPlace]:
    """Merge the same outlet from multiple suburb scans; aggregate pack positions (not only best)."""
    groups: dict[str, list[MapPackPlace]] = {}
    for p in pins:
        groups.setdefault(_competitor_dedupe_key(p), []).append(p)

    merged: list[MapPackPlace] = []
    for group in groups.values():
        ranks = [g.rank for g in group if g.rank is not None]
        best = min(ranks) if ranks else None
        worst = max(ranks) if ranks else None
        count = len(group)
        rep = min(group, key=lambda x: (x.rank if x.rank is not None else 999, x.title.lower()))
        merged.append(
            MapPackPlace(
                title=rep.title,
                lat=rep.lat,
                lng=rep.lng,
                rank=best,
                pack_rank_best=best,
                pack_rank_worst=worst,
                suburb_scan_count=count,
                domain=rep.domain,
                url=rep.url,
                address=rep.address,
                suburb_context=rep.suburb_context if count == 1 else None,
            )
        )

    merged.sort(
        key=lambda x: (x.pack_rank_best if x.pack_rank_best is not None else 999, x.title.lower()),
    )
    return merged[:limit]


async def _ahrefs_volume_by_suburb(
    keyword: str,
    suburbs: list[str],
    *,
    metro: str,
) -> dict[str, int]:
    """Batch Ahrefs overview for '{keyword} {suburb}' phrases."""
    keyword = keyword.strip()
    if not keyword or not suburbs:
        return {}
    country = _country_for_metro(metro)
    phrases = [f"{keyword} {s}".strip() for s in suburbs]
    client = AhrefsClient()
    try:
        rows = await client.keywords_overview(phrases, country=country)
    finally:
        await client.aclose()

    primary_l = keyword.lower()
    by_suburb: dict[str, int] = {s: 0 for s in suburbs}
    for row in rows:
        kw = str(row.get("keyword") or "").lower()
        vol = row.get("volume")
        v = int(vol) if isinstance(vol, int) else 0
        for suburb in suburbs:
            if suburb.lower() in kw and primary_l in kw:
                by_suburb[suburb] = max(by_suburb.get(suburb, 0), v)
    # Map exact phrase lookups
    for row in rows:
        kw = str(row.get("keyword") or "").lower()
        vol = row.get("volume")
        v = int(vol) if isinstance(vol, int) else 0
        for suburb in suburbs:
            if kw == f"{keyword} {suburb}".lower():
                by_suburb[suburb] = v
    return by_suburb


class RanksService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_suburbs(self, client_id: UUID) -> SuburbRanksResponse:
        client = (
            await self._session.execute(
                text(
                    "SELECT primary_keyword, metro_label FROM rp_clients WHERE client_id = :cid"
                ),
                {"cid": str(client_id)},
            )
        ).mappings().first()
        primary_kw = str(client["primary_keyword"] if client else "").strip()
        metro = str(client["metro_label"] if client else "")

        latest_scan = (
            await self._session.execute(
                text(
                    """
                    SELECT keyword
                    FROM rp_rank_history
                    WHERE client_id = :cid
                    ORDER BY checked_at DESC
                    LIMIT 1
                    """
                ),
                {"cid": str(client_id)},
            )
        ).mappings().first()
        keyword = str(latest_scan["keyword"] if latest_scan else "").strip() or scan_keyword_from_primary(primary_kw)

        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT DISTINCT ON (s.id)
                      s.id AS suburb_id,
                      s.suburb,
                      s.state,
                      s.postcode,
                      s.lat,
                      s.lng,
                      s.population,
                      r.rank_position,
                      r.feature_snapshot
                    FROM rp_suburb_grid s
                    LEFT JOIN rp_rank_history r
                      ON r.suburb_id = s.id
                     AND LOWER(TRIM(r.keyword)) = LOWER(TRIM(:kw))
                     AND r.client_id = :cid
                    WHERE s.client_id = :cid
                    ORDER BY s.id, r.checked_at DESC NULLS LAST
                    """
                ),
                {"kw": keyword, "cid": str(client_id)},
            )
        ).mappings().all()

        volume_source = "none"
        ahrefs_volumes: dict[str, int] = {}
        if get_ahrefs_api_key() and keyword and rows:
            suburb_names = [str(r["suburb"]) for r in rows]
            country = _country_for_metro(metro)
            vol_cache_key = build_cache_key(
                "ranks_volume",
                country,
                str(client_id),
                keyword,
                build_suburbs_hash(suburb_names),
            )
            cached_vols, _, _ = await get_ahrefs_cache(self._session, vol_cache_key)
            if isinstance(cached_vols, dict) and cached_vols.get("volumes"):
                ahrefs_volumes = {str(k): int(v) for k, v in cached_vols["volumes"].items()}
                volume_source = "ahrefs_cache"
            else:
                try:
                    ahrefs_volumes = await _ahrefs_volume_by_suburb(keyword, suburb_names, metro=metro)
                    volume_source = "ahrefs"
                    await set_ahrefs_cache(
                        self._session,
                        vol_cache_key,
                        {"volumes": ahrefs_volumes},
                        client_id=client_id,
                    )
                except Exception as exc:
                    logger.warning("Ahrefs volume batch for ranks failed: %s", exc)
                    volume_source = "ahrefs_error"

        out: list[SuburbRankRow] = []
        all_pack_pins: list[MapPackPlace] = []
        for r in rows:
            rank = r["rank_position"]
            suburb_name = str(r["suburb"])
            month_vol: int | None = None

            if volume_source in ("ahrefs", "ahrefs_cache") and suburb_name in ahrefs_volumes:
                month_vol = ahrefs_volumes[suburb_name]

            snap = r.get("feature_snapshot")
            if isinstance(snap, str):
                try:
                    snap = json.loads(snap)
                except json.JSONDecodeError:
                    snap = None
            if isinstance(snap, dict):
                if month_vol is None and volume_source != "ahrefs":
                    raw = snap.get("monthly_search_volume")
                    if raw is not None:
                        try:
                            month_vol = int(raw)
                        except (TypeError, ValueError):
                            month_vol = None
                all_pack_pins.extend(_pins_from_snapshot(snap))

            out.append(
                SuburbRankRow(
                    suburb_id=r["suburb_id"],
                    suburb=suburb_name,
                    state=str(r["state"]) if r["state"] is not None else None,
                    postcode=str(r["postcode"]) if r["postcode"] is not None else None,
                    lat=float(r["lat"]) if r["lat"] is not None else None,
                    lng=float(r["lng"]) if r["lng"] is not None else None,
                    population=r["population"],
                    rank_position=rank,
                    monthly_volume_proxy=month_vol if month_vol is not None else 0,
                )
            )

        out.sort(key=lambda x: (x.monthly_volume_proxy, x.population or 0), reverse=True)

        top3, page1, pack_11_20, notr = count_rank_bands(rows)
        vis = visibility_score_pct(rows)
        map_competitors = _dedupe_map_competitors(all_pack_pins)

        return SuburbRanksResponse(
            keyword=keyword,
            metro_label=metro,
            suburbs=out,
            visibility_score=vis,
            top3_count=top3,
            page1_count=page1,
            pack_11_20_count=pack_11_20,
            not_ranking_count=notr,
            map_competitors=map_competitors,
            volume_source=volume_source,
        )
