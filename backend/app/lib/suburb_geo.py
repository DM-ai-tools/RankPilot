"""Approximate suburb GeoJSON polygons (hex around lat/lng centre)."""

from __future__ import annotations

import math
from typing import Any


def hexagon_geojson(lat: float, lng: float, radius_m: float = 1100) -> dict[str, Any]:
    """GeoJSON Polygon — 6-point hex, ~radius_m from centre (WGS84)."""
    la = float(lat)
    lo = float(lng)
    r_deg = float(radius_m) / 111_320.0
    cos_lat = max(math.cos(math.radians(la)), 0.01)
    lng_scale = r_deg / cos_lat
    ring: list[list[float]] = []
    for i in range(6):
        ang = math.radians(60 * i - 30)
        ring.append([lo + lng_scale * math.cos(ang), la + r_deg * math.sin(ang)])
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def polygon_radius_for_population(pop: int | None) -> float:
    p = int(pop or 0)
    if p > 90_000:
        return 4_200.0
    if p > 35_000:
        return 3_500.0
    if p > 12_000:
        return 2_800.0
    if p > 4_000:
        return 2_200.0
    return 1_600.0
