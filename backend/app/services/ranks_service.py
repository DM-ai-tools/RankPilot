"""L1/L2: Suburb rank grid for visibility map."""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.lib.visibility_scoring import count_rank_bands, visibility_score_pct
from app.schemas.ranks import MapPackPlace, SuburbRankRow, SuburbRanksResponse


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
                domain=str(dom).strip()[:160] if dom else None,
                url=str(url).strip()[:400] if url else None,
                address=str(addr).strip()[:240] if addr else None,
                suburb_context=str(sub).strip()[:120] if sub else None,
            )
        )
    return pins


def _dedupe_map_competitors(pins: list[MapPackPlace], limit: int = 120) -> list[MapPackPlace]:
    """Prefer stronger (lower) pack rank when the same outlet appears from multiple suburb scans."""
    best: dict[str, MapPackPlace] = {}
    for p in pins:
        dom = (p.domain or "").strip().lower()
        key = (
            f"d:{dom}|{round(p.lat, 4)}|{round(p.lng, 4)}"
            if dom
            else f"t:{p.title.strip().lower()}|{round(p.lat, 4)}|{round(p.lng, 4)}"
        )
        cur = best.get(key)
        pr = p.rank if p.rank is not None else 999
        cr = cur.rank if cur is not None and cur.rank is not None else 999
        if cur is None or pr < cr:
            best[key] = p
    merged = sorted(best.values(), key=lambda x: (x.rank if x.rank is not None else 999, x.title.lower()))
    return merged[:limit]


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
        keyword = str(client["primary_keyword"] if client else "").strip()
        metro = str(client["metro_label"] if client else "")

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

        out: list[SuburbRankRow] = []
        all_pack_pins: list[MapPackPlace] = []
        for r in rows:
            rank = r["rank_position"]
            pop = int(r["population"] or 0)
            month_vol = None
            snap = r.get("feature_snapshot")
            if isinstance(snap, str):
                try:
                    snap = json.loads(snap)
                except json.JSONDecodeError:
                    snap = None
            if isinstance(snap, dict):
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
                    suburb=str(r["suburb"]),
                    state=str(r["state"]) if r["state"] is not None else None,
                    postcode=str(r["postcode"]) if r["postcode"] is not None else None,
                    lat=float(r["lat"]) if r["lat"] is not None else None,
                    lng=float(r["lng"]) if r["lng"] is not None else None,
                    population=r["population"],
                    rank_position=rank,
                    monthly_volume_proxy=month_vol if month_vol is not None else max(1, pop * 14 // 1000),
                )
            )

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
        )
