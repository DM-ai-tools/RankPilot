"""GA4 analytics endpoints — overview, pages, channels, geo, organic."""

from fastapi import APIRouter, Query

from app.deps import CurrentClientId, DbSession
from app.services.ga4_service import (
    RANGE_DAYS,
    fetch_channels,
    fetch_geo,
    fetch_organic_landing_pages,
    fetch_overview,
    fetch_pages,
)

router = APIRouter()

_RANGE_VALUES = list(RANGE_DAYS.keys())  # week, month, quarter, half, year


@router.get("/overview")
async def ga4_overview(
    client_id: CurrentClientId,
    session: DbSession,
    range: str = Query(default="month", description="week|month|quarter|half|year"),
    compare: bool = Query(default=False, description="Include previous-period totals"),
) -> dict:
    """Daily trend — users, sessions, bounce rate, engagement time."""
    return await fetch_overview(session, client_id, range_key=range, compare=compare)


@router.get("/pages")
async def ga4_pages(
    client_id: CurrentClientId,
    session: DbSession,
    range: str = Query(default="month"),
    compare: bool = Query(default=False),
    limit: int = Query(default=25, ge=5, le=100),
) -> dict:
    """Top pages by sessions with engagement metrics."""
    return await fetch_pages(session, client_id, range_key=range, compare=compare, limit=limit)


@router.get("/channels")
async def ga4_channels(
    client_id: CurrentClientId,
    session: DbSession,
    range: str = Query(default="month"),
    compare: bool = Query(default=False),
) -> dict:
    """Traffic by channel — organic, paid social, direct, referral, etc."""
    return await fetch_channels(session, client_id, range_key=range, compare=compare)


@router.get("/geo")
async def ga4_geo(
    client_id: CurrentClientId,
    session: DbSession,
    range: str = Query(default="month"),
    compare: bool = Query(default=False),
    limit: int = Query(default=30, ge=5, le=100),
) -> dict:
    """Top cities/suburbs by sessions."""
    return await fetch_geo(session, client_id, range_key=range, compare=compare, limit=limit)


@router.get("/organic")
async def ga4_organic(
    client_id: CurrentClientId,
    session: DbSession,
    range: str = Query(default="month"),
    compare: bool = Query(default=False),
    limit: int = Query(default=25, ge=5, le=100),
) -> dict:
    """Top landing pages from organic search only."""
    return await fetch_organic_landing_pages(
        session, client_id, range_key=range, compare=compare, limit=limit
    )
