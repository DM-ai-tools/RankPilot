"""Server-side coordinates for the tenant map pin: Nominatim → Google Places → AU metro CBD."""

from __future__ import annotations

import logging
import re
import time
from typing import Final

import httpx

from app.core.config import get_settings
from app.services.google_places_new_client import places_search_first_latlng

logger = logging.getLogger(__name__)

_NOMINATIM: Final[str] = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "RankPilot/1.0 (https://rankpilot.app; business map geocode)"

_cache: dict[str, tuple[float, float, float]] = {}
_TTL_S = 900.0

# WGS84 CBD-ish points when remote geocoders fail (still shows anchor like SERPMapper).
_AU_METRO_CENTROIDS: list[tuple[tuple[str, ...], tuple[float, float]]] = [
    (("melbourne", "vic"), (-37.8136, 144.9631)),
    (("sydney", "nsw"), (-33.8688, 151.2093)),
    (("brisbane", "qld"), (-27.4698, 153.0251)),
    (("perth", "wa"), (-31.9505, 115.8605)),
    (("adelaide", "sa"), (-34.9285, 138.6007)),
    (("canberra", "act"), (-35.2809, 149.1300)),
    (("hobart", "tas"), (-42.8821, 147.3272)),
    (("darwin", "nt"), (-12.4634, 130.8456)),
    (("gold coast", "qld"), (-28.0167, 153.4000)),
    (("newcastle", "nsw"), (-32.9283, 151.7817)),
    (("geelong", "vic"), (-38.1499, 144.3617)),
]


def _cache_get(key: str) -> tuple[float, float] | None:
    row = _cache.get(key)
    if not row:
        return None
    la, lo, ts = row
    if time.monotonic() - ts > _TTL_S:
        del _cache[key]
        return None
    return la, lo


def _cache_set(key: str, lat: float, lng: float) -> None:
    if len(_cache) > 800:
        _cache.clear()
    _cache[key] = (lat, lng, time.monotonic())


def au_metro_centroid(metro_label: str) -> tuple[float, float] | None:
    """Rough CBD when everything else fails — map still shows a pin."""
    s = re.sub(r"\s+", " ", (metro_label or "").lower().strip())
    if not s:
        return None
    for keys, pt in _AU_METRO_CENTROIDS:
        if all(k in s for k in keys):
            return pt
    for keys, pt in _AU_METRO_CENTROIDS:
        if keys[0] in s:
            return pt
    return None


async def nominatim_lookup(query: str) -> tuple[float, float] | None:
    q = (query or "").strip()
    if len(q) < 4:
        return None
    ck = q.lower()[:200]
    hit = _cache_get(ck)
    if hit:
        return hit
    params = {"format": "json", "limit": "1", "q": q}
    headers = {"User-Agent": _USER_AGENT, "Accept-Language": "en"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(6.0, connect=4.0)) as client:
            r = await client.get(_NOMINATIM, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        logger.warning("Nominatim geocode failed for %r: %s", q[:80], exc)
        return None
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    if not isinstance(first, dict):
        return None
    try:
        la = float(first["lat"])
        lo = float(first["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= la <= 90) or not (-180 <= lo <= 180):
        return None
    _cache_set(ck, la, lo)
    return la, lo


async def resolve_business_map_point(
    *,
    business_address: str,
    business_name: str,
    metro_label: str,
) -> tuple[float, float, str] | None:
    """Return (lat, lng, source) for the blue business anchor.

    Order: street address → name+metro → metro only → Google Places (New) → AU metro CBD.
    """
    addr = (business_address or "").strip()
    name = (business_name or "").strip()
    metro = (metro_label or "").strip()

    if len(addr) >= 6:
        pt = await nominatim_lookup(addr)
        if pt:
            return pt[0], pt[1], "address"

    if name and metro:
        pt = await nominatim_lookup(f"{name}, {metro}, Australia")
        if pt:
            return pt[0], pt[1], "name_metro"
        pt = await nominatim_lookup(f"{name} {metro} Australia")
        if pt:
            return pt[0], pt[1], "name_metro"

    if metro:
        pt = await nominatim_lookup(f"{metro}, Australia")
        if pt:
            return pt[0], pt[1], "metro_area"

    api_key = (get_settings().google_places_api_key or "").strip()
    if api_key and (addr or (name and metro)):
        qtext = addr if len(addr) >= 6 else f"{name} {metro} Australia"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=4.0)) as client:
                gl = await places_search_first_latlng(client, api_key, qtext)
            if gl:
                return gl[0], gl[1], "google_places"
        except Exception as exc:
            logger.warning("Google Places map pin lookup failed: %s", exc)

    fb = au_metro_centroid(metro)
    if fb:
        return fb[0], fb[1], "metro_fallback"

    return None
