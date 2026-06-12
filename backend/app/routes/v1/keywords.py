"""Keyword research — Ahrefs live data + suburb suggestions."""

import logging

from fastapi import APIRouter, Query

from app.deps import CurrentClientId, DbSession

from pydantic import BaseModel

from app.schemas.keywords import (
    CompetitorGbpPostsResponse,
    KeywordLookupResponse,
    KeywordOverviewResponse,
    KeywordSerpCompetitorsResponse,
    SiteKeywordsResponse,
    SuburbKeywordResearchResponse,
)
from app.services.competitor_gbp_posts_service import fetch_competitor_gbp_posts
from app.services.competitor_keywords_service import (
    fetch_competitor_site_keywords,
    fetch_keyword_serp_competitors,
)
from app.services.keyword_tracker_service import (
    add_keyword,
    get_keyword_tracker_list,
    remove_keyword,
    run_rank_checks,
    sync_tracked_keywords,
)
from app.services.keyword_lookup_service import lookup_keywords
from app.services.keyword_overview_service import fetch_keyword_overview
from app.services.keyword_research_service import fetch_suburb_keyword_research

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/suburb-research", response_model=SuburbKeywordResearchResponse)
async def suburb_keyword_research(
    client_id: CurrentClientId,
    session: DbSession,
    suburb_limit: int = Query(default=8, ge=1, le=12),
    idea_limit: int = Query(default=25, ge=5, le=50),
    refresh: bool = Query(default=False, description="Bypass 24h Ahrefs cache"),
) -> SuburbKeywordResearchResponse:
    """Live search volumes, KD, and related keywords for suburbs in the client's grid."""
    result = await fetch_suburb_keyword_research(
        session,
        client_id,
        suburb_limit=suburb_limit,
        idea_limit=idea_limit,
        force_refresh=refresh,
    )
    logger.info("suburb-research client=%s source=%s phrases=%d", client_id, result.source, len(result.suburb_phrases))
    return result


@router.get("/overview", response_model=KeywordOverviewResponse)
async def keyword_overview(
    client_id: CurrentClientId,
    session: DbSession,
    keyword: str = Query(..., min_length=1, max_length=200),
    country: str | None = Query(default=None, min_length=2, max_length=2),
    refresh: bool = Query(default=False, description="Bypass 24h Ahrefs cache"),
) -> KeywordOverviewResponse:
    """Ahrefs-style overview: KD, volume, traffic potential, global volume, keyword ideas."""
    return await fetch_keyword_overview(
        session, client_id, keyword=keyword, country=country, force_refresh=refresh
    )


@router.get("/site-keywords", response_model=SiteKeywordsResponse)
async def competitor_site_keywords(
    client_id: CurrentClientId,
    session: DbSession,
    target: str = Query(..., min_length=3, max_length=300, description="Competitor website/domain"),
    country: str | None = Query(default=None, min_length=2, max_length=2),
    limit: int = Query(default=100, ge=10, le=200),
    refresh: bool = Query(default=False, description="Bypass 24h Ahrefs cache"),
) -> SiteKeywordsResponse:
    """Organic keywords a competitor website ranks for (Ahrefs Site Explorer)."""
    result = await fetch_competitor_site_keywords(
        session, client_id, target=target, country=country, limit=limit, force_refresh=refresh
    )
    logger.info("site-keywords client=%s target=%s n=%d", client_id, result.target, len(result.keywords))
    return result


@router.get("/serp-competitors", response_model=KeywordSerpCompetitorsResponse)
async def keyword_serp_competitors(
    client_id: CurrentClientId,
    session: DbSession,
    keyword: str = Query(..., min_length=1, max_length=200),
    country: str | None = Query(default=None, min_length=2, max_length=2),
    refresh: bool = Query(default=False, description="Bypass 24h Ahrefs cache"),
) -> KeywordSerpCompetitorsResponse:
    """Competitors ranking on Google for this keyword (Ahrefs SERP overview)."""
    return await fetch_keyword_serp_competitors(
        session, client_id, keyword=keyword, country=country, force_refresh=refresh
    )


@router.get("/competitor-gbp-posts", response_model=CompetitorGbpPostsResponse)
async def competitor_gbp_posts(
    client_id: CurrentClientId,
    session: DbSession,
    keyword: str = Query(..., min_length=1, max_length=200),
    serp_targets: str | None = Query(
        default=None,
        description="JSON array of SERP competitors {domain,title,position,in_local_pack,local_pack_position}",
    ),
    refresh: bool = Query(default=False, description="Bypass 24h cache"),
) -> CompetitorGbpPostsResponse:
    """How competitors use GBP posts — defaults to same organic SERP rivals shown in the UI."""
    result = await fetch_competitor_gbp_posts(
        session, client_id, keyword=keyword, serp_targets=serp_targets, force_refresh=refresh
    )
    logger.info(
        "competitor-gbp-posts client=%s keyword=%s competitors=%d",
        client_id, keyword, len(result.competitors),
    )
    return result


class _AddKwBody(BaseModel):
    keyword: str


@router.get("/tracker")
async def get_tracker(
    client_id: CurrentClientId,
    session: DbSession,
) -> list[dict]:
    """All tracked keywords with latest organic + Maps positions and 12-week trend."""
    return await get_keyword_tracker_list(session, client_id)


@router.post("/tracker/sync")
async def sync_tracker(
    client_id: CurrentClientId,
    session: DbSession,
    force: bool = Query(default=False, description="Re-check even if checked today"),
    keyword: str | None = Query(
        default=None,
        description="Optional single keyword to refresh (faster than full sync)",
    ),
) -> dict:
    """Import keywords from GBP posts + run rank checks for all tracked keywords."""
    added = await sync_tracked_keywords(session, client_id)
    kw_list = [keyword.strip().lower()] if keyword and keyword.strip() else None
    results = await run_rank_checks(
        session, client_id, keywords=kw_list, force=force or bool(kw_list)
    )
    return {"added_keywords": added, "checked": len(results), "results": results}


@router.post("/tracker/add")
async def tracker_add_keyword(
    body: _AddKwBody,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    """Manually add a keyword to track."""
    is_new = await add_keyword(session, client_id, body.keyword)
    if is_new:
        await run_rank_checks(session, client_id, keywords=[body.keyword.strip().lower()])
    return {"keyword": body.keyword.strip().lower(), "added": is_new}


@router.delete("/tracker/{keyword:path}")
async def tracker_remove_keyword(
    keyword: str,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    """Stop tracking a keyword."""
    await remove_keyword(session, client_id, keyword)
    return {"keyword": keyword, "removed": True}


@router.get("/lookup", response_model=KeywordLookupResponse)
async def keyword_lookup(
    client_id: CurrentClientId,
    session: DbSession,
    q: str = Query(default="", min_length=0, max_length=2000, description="Comma/newline-separated keywords"),
    country: str | None = Query(default=None, min_length=2, max_length=2),
    refresh: bool = Query(default=False, description="Bypass 24h Ahrefs cache"),
) -> KeywordLookupResponse:
    """Look up volume, keyword difficulty, and opportunity score (Ahrefs)."""
    return await lookup_keywords(session, client_id, query=q, country=country, force_refresh=refresh)
