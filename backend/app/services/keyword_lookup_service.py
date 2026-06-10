"""Ad-hoc keyword metrics lookup (Ahrefs)."""

from __future__ import annotations

import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_ahrefs_api_key, get_settings
from app.schemas.keywords import KeywordLookupItem, KeywordLookupResponse
from app.services.ahrefs_cache_service import (
    build_lookup_cache_key,
    cache_timestamps_iso,
    get_ahrefs_cache,
    set_ahrefs_cache,
)
from app.services.ahrefs_service import AhrefsClient
def _parse_keyword_input(raw: str, *, max_items: int = 20) -> list[str]:
    parts = re.split(r"[\n,;]+", raw or "")
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        k = re.sub(r"\s+", " ", p.strip())
        if not k or len(k) > 120:
            continue
        low = k.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(k)
        if len(out) >= max_items:
            break
    return out


def _country_for_metro(metro: str) -> str:
    m = (metro or "").upper()
    if ", NSW" in m or ", VIC" in m or ", QLD" in m or ", SA" in m or ", WA" in m or ", TAS" in m:
        return "au"
    if ", NZ" in m or "AUCKLAND" in m:
        return "nz"
    if ", UK" in m or "LONDON" in m:
        return "gb"
    if ", USA" in m or ", CA" in m and "CANADA" not in m:
        return "us"
    if "CANADA" in m or ", ON" in m:
        return "ca"
    return "au"


async def lookup_keywords(
    session: AsyncSession,
    client_id: UUID,
    *,
    query: str,
    keywords: list[str] | None = None,
    country: str | None = None,
    force_refresh: bool = False,
) -> KeywordLookupResponse:
    if not get_ahrefs_api_key():
        return KeywordLookupResponse(
            message="Set AHREFS_API_KEY in backend/.env — keyword features use Ahrefs only (not DataForSEO).",
            source="none",
        )

    settings = get_settings()

    profile = (
        await session.execute(
            text("SELECT metro_label FROM rp_clients WHERE client_id = :cid LIMIT 1"),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    metro = str((profile or {}).get("metro_label") or "")
    cc = (country or _country_for_metro(metro) or "au").strip().lower()[:2]

    kws = list(keywords or []) if keywords else _parse_keyword_input(query)
    if not kws:
        raise HTTPException(status_code=400, detail="Enter at least one keyword to look up.")

    cache_key = build_lookup_cache_key(cc, kws)
    if not force_refresh:
        cached, fetched_at, expires_at = await get_ahrefs_cache(session, cache_key)
        if cached:
            cached_at_s, expires_s = cache_timestamps_iso(fetched_at, expires_at)
            out = KeywordLookupResponse.model_validate(cached)
            out.from_cache = True
            out.cached_at = cached_at_s
            out.cache_expires_at = expires_s
            return out

    client = AhrefsClient(settings)
    try:
        rows = await client.keywords_overview(kws, country=cc)
    finally:
        await client.aclose()

    by_kw = {r["keyword"].lower(): r for r in rows if r.get("keyword")}
    items: list[KeywordLookupItem] = []
    for kw in kws:
        row = by_kw.get(kw.lower(), {})
        items.append(
            KeywordLookupItem(
                keyword=kw,
                volume=int(row.get("volume") or 0),
                difficulty=row.get("difficulty"),
                competition=row.get("competition"),
                traffic_potential=row.get("traffic_potential"),
                cpc_cents=row.get("cpc_cents"),
                opportunity_score=int(row.get("opportunity_score") or 0),
            )
        )
    items.sort(key=lambda x: x.opportunity_score, reverse=True)

    response = KeywordLookupResponse(country=cc, keywords=items, source="ahrefs", message=None)
    await set_ahrefs_cache(
        session,
        cache_key,
        response.model_dump(mode="json", exclude={"from_cache", "cached_at", "cache_expires_at"}),
        client_id=client_id,
    )
    return response
