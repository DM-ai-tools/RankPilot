"""Google Places API (New) — Text Search + Place Details.

Maps Platform keys often only allow **Places API (New)**. Legacy URLs
``/maps/api/place/*/json`` return REQUEST_DENIED for those projects.
"""

from __future__ import annotations

from urllib.parse import quote

import httpx

_PLACES_V1 = "https://places.googleapis.com/v1"


def normalize_place_id(place_id: str) -> str:
    p = (place_id or "").strip()
    if p.startswith("places/"):
        return p.split("/", 1)[1]
    return p


def display_name_text(place: dict) -> str:
    dn = place.get("displayName")
    if isinstance(dn, dict):
        return str(dn.get("text") or "").strip()
    return ""


async def places_search_text(
    client: httpx.AsyncClient,
    api_key: str,
    text_query: str,
    *,
    page_size: int = 10,
    field_mask: str = "places.id,places.displayName,places.formattedAddress,places.websiteUri",
) -> list[dict]:
    """POST places:searchText — returns ``places`` list (may be empty)."""
    url = f"{_PLACES_V1}/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": field_mask,
    }
    body = {"textQuery": text_query.strip(), "pageSize": min(20, max(1, page_size))}
    r = await client.post(url, headers=headers, json=body)
    r.raise_for_status()
    data = r.json()
    places = data.get("places")
    return places if isinstance(places, list) else []


async def places_search_first_latlng(
    client: httpx.AsyncClient,
    api_key: str,
    text_query: str,
) -> tuple[float, float] | None:
    """First Places hit with geometry — for map pins when Nominatim is unavailable."""
    places = await places_search_text(
        client,
        api_key,
        text_query,
        page_size=3,
        field_mask="places.displayName,places.location",
    )
    for p in places:
        if not isinstance(p, dict):
            continue
        loc = p.get("location")
        if not isinstance(loc, dict):
            continue
        try:
            la = float(loc["latitude"])
            lo = float(loc["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if -90 <= la <= 90 and -180 <= lo <= 180:
            return la, lo
    return None


async def place_details(
    client: httpx.AsyncClient,
    api_key: str,
    place_id: str,
) -> dict | None:
    """GET v1/places/{id} — field mask required."""
    pid = normalize_place_id(place_id)
    if not pid:
        return None
    url = f"{_PLACES_V1}/places/{quote(pid, safe='')}"
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": ",".join(
            [
                "id",
                "displayName",
                "formattedAddress",
                "nationalPhoneNumber",
                "internationalPhoneNumber",
                "websiteUri",
                "googleMapsUri",
            ]
        ),
    }
    r = await client.get(url, headers=headers)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, dict) else None
