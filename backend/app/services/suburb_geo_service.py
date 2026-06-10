"""Suburb boundary GeoJSON for Leaflet maps."""

from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.au_suburbs import METRO_SUBURBS
from app.lib.suburb_geo import hexagon_geojson, polygon_radius_for_population

logger = logging.getLogger(__name__)


async def _table_exists(session: AsyncSession) -> bool:
    row = await session.execute(text("SELECT to_regclass('public.rp_suburb_geo')"))
    return row.scalar() is not None


async def ensure_suburb_geo_seeded(session: AsyncSession) -> None:
    """Populate rp_suburb_geo from curated metro lists if empty."""
    if not await _table_exists(session):
        return
    n = (await session.execute(text("SELECT COUNT(*) FROM rp_suburb_geo"))).scalar() or 0
    if int(n) > 0:
        return

    rows: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for suburbs in METRO_SUBURBS.values():
        for s in suburbs:
            suburb = str(s.get("suburb") or "").strip()
            state = str(s.get("state") or "").strip().upper()
            postcode = str(s.get("postcode") or "").strip()
            if not suburb:
                continue
            key = (suburb, state, postcode)
            if key in seen:
                continue
            seen.add(key)
            try:
                la = float(s["lat"])
                lo = float(s["lng"])
            except (KeyError, TypeError, ValueError):
                continue
            pop = s.get("population")
            poly = hexagon_geojson(la, lo, polygon_radius_for_population(int(pop or 0)))
            rows.append(
                {
                    "suburb": suburb,
                    "state": state or None,
                    "postcode": postcode or None,
                    "lat": la,
                    "lng": lo,
                    "poly": json.dumps(poly),
                }
            )

    for r in rows:
        await session.execute(
            text(
                """
                INSERT INTO rp_suburb_geo (suburb, state, postcode, lat, lng, geojson_polygon)
                VALUES (:suburb, :state, :postcode, :lat, :lng, (CAST(:poly AS text))::jsonb)
                ON CONFLICT (suburb, state, postcode) DO NOTHING
                """
            ),
            r,
        )
    await session.commit()
    logger.info("Seeded rp_suburb_geo with %d suburb hex polygons", len(rows))


async def fetch_suburb_geo(
    session: AsyncSession,
    client_id: UUID,
    suburb_ids: list[str],
) -> dict:
    if not suburb_ids:
        return {"items": []}

    ids = [str(x).strip() for x in suburb_ids[:100] if str(x).strip()]
    if not ids:
        return {"items": []}

    await ensure_suburb_geo_seeded(session)

    if not await _table_exists(session):
        # Table missing — generate on the fly from grid lat/lng only.
        placeholders = ", ".join(f":id{i}" for i in range(len(ids)))
        params: dict = {"cid": str(client_id)}
        for i, sid in enumerate(ids):
            params[f"id{i}"] = sid
        grid_rows = (
            await session.execute(
                text(
                    f"""
                    SELECT id, suburb, state, postcode, lat, lng, population
                    FROM rp_suburb_grid
                    WHERE client_id = :cid AND id::text IN ({placeholders})
                    """
                ),
                params,
            )
        ).mappings().all()
        items = []
        for r in grid_rows:
            la, lo = r.get("lat"), r.get("lng")
            if la is None or lo is None:
                continue
            pop = r.get("population")
            poly = hexagon_geojson(float(la), float(lo), polygon_radius_for_population(int(pop or 0)))
            items.append(
                {
                    "suburb_id": str(r["id"]),
                    "suburb": str(r["suburb"]),
                    "lat": float(la),
                    "lng": float(lo),
                    "geojson_polygon": poly,
                }
            )
        return {"items": items}

    placeholders = ", ".join(f":id{i}" for i in range(len(ids)))
    params = {"cid": str(client_id)}
    for i, sid in enumerate(ids):
        params[f"id{i}"] = sid

    rows = (
        await session.execute(
            text(
                f"""
                SELECT
                  s.id AS suburb_id,
                  s.suburb,
                  s.state,
                  s.postcode,
                  s.lat,
                  s.lng,
                  s.population,
                  g.geojson_polygon
                FROM rp_suburb_grid s
                LEFT JOIN rp_suburb_geo g
                  ON g.suburb = s.suburb
                 AND COALESCE(g.state, '') = COALESCE(s.state, '')
                 AND COALESCE(g.postcode, '') = COALESCE(s.postcode, '')
                WHERE s.client_id = :cid
                  AND s.id::text IN ({placeholders})
                """
            ),
            params,
        )
    ).mappings().all()

    items: list[dict] = []
    for r in rows:
        la, lo = r.get("lat"), r.get("lng")
        if la is None or lo is None:
            continue
        poly = r.get("geojson_polygon")
        if isinstance(poly, str):
            try:
                poly = json.loads(poly)
            except json.JSONDecodeError:
                poly = None
        if not isinstance(poly, dict):
            pop = r.get("population")
            poly = hexagon_geojson(float(la), float(lo), polygon_radius_for_population(int(pop or 0)))
        items.append(
            {
                "suburb_id": str(r["suburb_id"]),
                "suburb": str(r["suburb"]),
                "lat": float(la),
                "lng": float(lo),
                "geojson_polygon": poly,
            }
        )
    return {"items": items}
