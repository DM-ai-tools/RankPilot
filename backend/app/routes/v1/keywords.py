"""Keyword research — Ahrefs live data + suburb suggestions."""

import logging

from fastapi import APIRouter, Query

from app.deps import CurrentClientId, DbSession

from app.schemas.keywords import KeywordLookupResponse, KeywordOverviewResponse, SuburbKeywordResearchResponse
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
