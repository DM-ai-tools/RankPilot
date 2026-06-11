"""Ahrefs Site Explorer — organic keywords a competitor website ranks for."""

from __future__ import annotations

import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_ahrefs_api_key
from app.schemas.keywords import (
    KeywordSerpCompetitorsResponse,
    SerpCompetitorItem,
    SiteKeywordItem,
    SiteKeywordsResponse,
)
from app.services.ahrefs_cache_service import (
    build_cache_key,
    cache_timestamps_iso,
    get_ahrefs_cache,
    set_ahrefs_cache,
)
from app.services.ahrefs_service import AhrefsClient
from app.services.keyword_lookup_service import _country_for_metro

_COUNTRY_LABELS: dict[str, str] = {
    "au": "Australia",
    "nz": "New Zealand",
    "us": "United States",
    "gb": "United Kingdom",
    "ca": "Canada",
}


def normalize_target_domain(raw: str) -> str:
    """'https://www.example.com.au/services/' -> 'example.com.au'."""
    t = (raw or "").strip().lower()
    t = re.sub(r"^[a-z][a-z0-9+.-]*://", "", t)  # scheme
    t = t.split("/")[0].split("?")[0].split("#")[0]  # path/query
    t = t.split("@")[-1].split(":")[0]  # creds / port
    if t.startswith("www."):
        t = t[4:]
    return t


async def fetch_keyword_serp_competitors(
    session: AsyncSession,
    client_id: UUID,
    *,
    keyword: str,
    country: str | None = None,
    top_positions: int = 8,
    force_refresh: bool = False,
) -> KeywordSerpCompetitorsResponse:
    """Who ranks on Google for this keyword (Ahrefs SERP overview, 24h cached)."""
    keyword = " ".join((keyword or "").split()).strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword is required.")

    if not get_ahrefs_api_key():
        return KeywordSerpCompetitorsResponse(
            keyword=keyword,
            message="Set AHREFS_API_KEY in backend/.env and restart the API.",
            source="none",
        )

    profile = (
        await session.execute(
            text("SELECT metro_label FROM rp_clients WHERE client_id = :cid LIMIT 1"),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    metro = str((profile or {}).get("metro_label") or "")
    cc = (country or _country_for_metro(metro) or "au").strip().lower()[:2]
    # v2: includes Google Maps local-pack data
    cache_key = build_cache_key("serp-competitors-v2", cc, keyword)

    if not force_refresh:
        cached, fetched_at, expires_at = await get_ahrefs_cache(session, cache_key)
        if cached:
            cached_at_s, expires_s = cache_timestamps_iso(fetched_at, expires_at)
            out = KeywordSerpCompetitorsResponse.model_validate(cached)
            out.from_cache = True
            out.cached_at = cached_at_s
            out.cache_expires_at = expires_s
            return out

    client = AhrefsClient()
    try:
        rows = await client.serp_overview(keyword, country=cc, top_positions=top_positions)
    finally:
        await client.aclose()

    # Merge organic + Google Maps local-pack appearances per domain.
    by_domain: dict[str, SerpCompetitorItem] = {}
    for row in rows:
        url = str(row.get("url") or "")
        domain = normalize_target_domain(url)
        if not domain:
            continue
        kinds = row.get("types") or []
        is_local = "local_pack" in kinds
        is_organic = "organic" in kinds or not kinds
        pos = row.get("position")

        item = by_domain.get(domain)
        if item is None:
            item = SerpCompetitorItem(
                position=pos if is_organic else None,
                domain=domain,
                url=url,
                title=row.get("title"),
                traffic=row.get("traffic"),
                in_local_pack=is_local,
                local_pack_position=pos if is_local else None,
            )
            by_domain[domain] = item
            continue
        if is_organic and item.position is None:
            item.position = pos
            item.url = url
            item.title = item.title or row.get("title")
        if is_local:
            item.in_local_pack = True
            if item.local_pack_position is None:
                item.local_pack_position = pos

    # Organic ranks first (best position first), Maps-pack-only entries after.
    competitors = sorted(
        by_domain.values(),
        key=lambda c: (c.position is None, c.position or 0, c.local_pack_position or 99),
    )

    response = KeywordSerpCompetitorsResponse(
        keyword=keyword,
        country=cc,
        competitors=competitors,
        source="ahrefs",
        message=None if competitors else f"No Google results found for “{keyword}” in {cc.upper()}.",
        from_cache=False,
    )
    await set_ahrefs_cache(
        session,
        cache_key,
        response.model_dump(mode="json", exclude={"from_cache", "cached_at", "cache_expires_at"}),
        client_id=client_id,
    )
    return response


async def fetch_competitor_site_keywords(
    session: AsyncSession,
    client_id: UUID,
    *,
    target: str,
    country: str | None = None,
    limit: int = 100,
    force_refresh: bool = False,
) -> SiteKeywordsResponse:
    domain = normalize_target_domain(target)
    if not domain or "." not in domain:
        raise HTTPException(status_code=400, detail="Enter a valid competitor website, e.g. example.com.au")

    if not get_ahrefs_api_key():
        return SiteKeywordsResponse(
            target=domain,
            message="Set AHREFS_API_KEY in backend/.env and restart the API.",
            source="none",
        )

    profile = (
        await session.execute(
            text("SELECT metro_label FROM rp_clients WHERE client_id = :cid LIMIT 1"),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    metro = str((profile or {}).get("metro_label") or "")
    cc = (country or _country_for_metro(metro) or "au").strip().lower()[:2]
    cache_key = build_cache_key("site-keywords", cc, domain)

    if not force_refresh:
        cached, fetched_at, expires_at = await get_ahrefs_cache(session, cache_key)
        if cached:
            cached_at_s, expires_s = cache_timestamps_iso(fetched_at, expires_at)
            out = SiteKeywordsResponse.model_validate(cached)
            out.from_cache = True
            out.cached_at = cached_at_s
            out.cache_expires_at = expires_s
            return out

    client = AhrefsClient()
    try:
        rows = await client.site_organic_keywords(domain, country=cc, limit=limit)
    finally:
        await client.aclose()

    items: list[SiteKeywordItem] = []
    seen: set[str] = set()
    for row in rows:
        kw = str(row.get("keyword") or "").strip()
        if not kw or kw.lower() in seen:
            continue
        seen.add(kw.lower())
        items.append(
            SiteKeywordItem(
                keyword=kw,
                volume=row.get("volume"),
                volume_display=str(row.get("volume_display") or "—"),
                difficulty=row.get("difficulty"),
                competition=row.get("competition"),
                best_position=row.get("best_position"),
                traffic=row.get("traffic"),
                ranking_url=row.get("ranking_url"),
                opportunity_score=int(row.get("opportunity_score") or 0),
            )
        )

    response = SiteKeywordsResponse(
        target=domain,
        country=cc,
        country_label=_COUNTRY_LABELS.get(cc, cc.upper()),
        keywords=items,
        source="ahrefs",
        message=None if items else f"Ahrefs found no organic keywords for {domain} in {cc.upper()}.",
        from_cache=False,
    )
    await set_ahrefs_cache(
        session,
        cache_key,
        response.model_dump(mode="json", exclude={"from_cache", "cached_at", "cache_expires_at"}),
        client_id=client_id,
    )
    return response
