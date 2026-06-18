"""GA4 analytics endpoints — overview, pages, channels, geo, organic."""

import json
import logging

import httpx
from fastapi import APIRouter, Query

from app.deps import CurrentClientId, DbSession
from app.routes.v1.integrations import _get_google_access_token, _get_integration_row
from app.services.ga4_service import (
    RANGE_DAYS,
    _GA4_DATA_URL,
    fetch_channels,
    fetch_geo,
    fetch_organic_landing_pages,
    fetch_overview,
    fetch_pages,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_RANGE_VALUES = list(RANGE_DAYS.keys())  # week, month, quarter, half, year


@router.get("/debug")
async def ga4_debug(client_id: CurrentClientId, session: DbSession) -> dict:
    """Diagnostic: shows stored property_id and tests the Data API with a minimal call."""
    # 1. Check integration row
    row = await _get_integration_row(session, client_id, "ga4")
    extra = row.get("extra_data") or {}
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except Exception:
            extra = {}

    property_id = str(extra.get("selected_property") or "").strip()
    has_access_token = bool(row.get("access_token"))
    has_refresh_token = bool(row.get("refresh_token"))
    token_expiry = str(row.get("token_expiry") or "unknown")

    result: dict = {
        "property_id_stored": property_id or "(none)",
        "has_access_token": has_access_token,
        "has_refresh_token": has_refresh_token,
        "token_expiry": token_expiry,
        "extra_data_keys": list(extra.keys()) if extra else [],
    }

    if not property_id:
        result["error"] = "No GA4 property selected in extra_data. Go to Business Setup and select a property."
        return result

    # 2. Get a fresh token
    try:
        token = await _get_google_access_token(session, client_id, "ga4")
        result["token_refresh_ok"] = True
    except Exception as exc:
        result["token_refresh_ok"] = False
        result["token_refresh_error"] = str(exc)
        return result

    # 3. Minimal runReport test
    url = _GA4_DATA_URL.format(property_id=property_id)
    result["data_api_url"] = url
    body = {
        "dateRanges": [{"startDate": "7daysAgo", "endDate": "today"}],
        "metrics": [{"name": "activeUsers"}],
        "limit": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as http:
            r = await http.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
        result["data_api_status"] = r.status_code
        if r.is_success:
            result["data_api_ok"] = True
            result["sample_row_count"] = (r.json().get("rowCount") or 0)
        else:
            result["data_api_ok"] = False
            raw = r.text[:800]
            try:
                err = r.json().get("error", {})
                result["google_error_message"] = str(err.get("message") or raw)
                result["google_error_status"] = str(err.get("status") or "")
                result["google_error_details"] = err.get("details") or []
            except Exception:
                result["google_error_raw"] = raw
    except Exception as exc:
        result["data_api_ok"] = False
        result["data_api_exception"] = str(exc)

    return result


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
