"""GA4 Data API v1beta — runReport wrapper for RankPilot analytics page."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

logger = logging.getLogger(__name__)

_GA4_DATA_URL = "https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport"

# ── Date ranges ──────────────────────────────────────────────────────────────

RANGE_DAYS: dict[str, int] = {
    "week": 7,
    "month": 30,
    "quarter": 90,
    "half": 180,
    "year": 365,
}


def _date_range(range_key: str) -> tuple[str, str]:
    days = RANGE_DAYS.get(range_key, 30)
    end = date.today()
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def _comparison_range(range_key: str) -> tuple[str, str]:
    days = RANGE_DAYS.get(range_key, 30)
    end = date.today() - timedelta(days=days)
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def _build_date_ranges(range_key: str, compare: bool) -> list[dict]:
    start, end = _date_range(range_key)
    ranges = [{"startDate": start, "endDate": end, "name": "current"}]
    if compare:
        cs, ce = _comparison_range(range_key)
        ranges.append({"startDate": cs, "endDate": ce, "name": "previous"})
    return ranges


# ── Low-level API call ────────────────────────────────────────────────────────

async def _run_report(
    token: str,
    property_id: str,
    *,
    dimensions: list[dict],
    metrics: list[dict],
    date_ranges: list[dict],
    dimension_filter: dict | None = None,
    order_bys: list[dict] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    url = _GA4_DATA_URL.format(property_id=property_id)
    body: dict[str, Any] = {
        "dimensions": dimensions,
        "metrics": metrics,
        "dateRanges": date_ranges,
        "limit": limit,
        "offset": offset,
    }
    if dimension_filter:
        body["dimensionFilter"] = dimension_filter
    if order_bys:
        body["orderBys"] = order_bys

    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            r = await http.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GA4 API request failed: {exc}",
        ) from exc

    if r.status_code == 403:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="GA4 access denied — reconnect GA4 in Business Setup.",
        )
    if r.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="GA4 property not found. Reselect your GA4 property in Business Setup.",
        )
    if not r.is_success:
        detail = r.text[:300]
        try:
            detail = r.json().get("error", {}).get("message") or detail
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GA4 API error ({r.status_code}): {detail}",
        )
    return r.json()


# ── Response parsers ──────────────────────────────────────────────────────────

def _parse_rows(data: dict) -> list[dict[str, Any]]:
    dim_headers = [h["name"] for h in (data.get("dimensionHeaders") or [])]
    met_headers = [h["name"] for h in (data.get("metricHeaders") or [])]
    out: list[dict[str, Any]] = []
    for row in (data.get("rows") or []):
        record: dict[str, Any] = {}
        for i, dim in enumerate((row.get("dimensionValues") or [])):
            key = dim_headers[i] if i < len(dim_headers) else f"dim_{i}"
            record[key] = dim.get("value") or ""
        for i, met in enumerate((row.get("metricValues") or [])):
            key = met_headers[i] if i < len(met_headers) else f"met_{i}"
            raw = met.get("value") or "0"
            try:
                record[key] = float(raw) if "." in raw else int(raw)
            except ValueError:
                record[key] = raw
        out.append(record)
    return out


def _row_totals(data: dict) -> dict[str, Any]:
    met_headers = [h["name"] for h in (data.get("metricHeaders") or [])]
    totals: dict[str, Any] = {}
    for tot_list in (data.get("totals") or []):
        date_range = tot_list.get("dimensionValues", [{}])[0].get("value") or "current"
        vals: dict[str, Any] = {}
        for i, met in enumerate((tot_list.get("metricValues") or [])):
            key = met_headers[i] if i < len(met_headers) else f"met_{i}"
            raw = met.get("value") or "0"
            try:
                vals[key] = float(raw) if "." in raw else int(raw)
            except ValueError:
                vals[key] = raw
        totals[date_range] = vals
    return totals


# ── High-level fetch functions ────────────────────────────────────────────────

async def fetch_overview(
    session: AsyncSession,
    client_id: UUID,
    *,
    range_key: str = "month",
    compare: bool = False,
) -> dict[str, Any]:
    """Daily trend of users, sessions, new users, bounce rate and engagement time."""
    from app.routes.v1.integrations import _get_google_access_token, _get_integration_row  # noqa: PLC0415

    token = await _get_google_access_token(session, client_id, "ga4")
    row = await _get_integration_row(session, client_id, "ga4")
    extra = row.get("extra_data") or {}
    if isinstance(extra, str):
        import json
        try:
            extra = json.loads(extra)
        except Exception:
            extra = {}
    property_id = str(extra.get("selected_property") or "").strip()
    if not property_id:
        raise HTTPException(status_code=400, detail="No GA4 property selected. Choose one in Business Setup.")

    date_ranges = _build_date_ranges(range_key, compare)

    data = await _run_report(
        token,
        property_id,
        dimensions=[{"name": "date"}],
        metrics=[
            {"name": "activeUsers"},
            {"name": "newUsers"},
            {"name": "sessions"},
            {"name": "averageSessionDuration"},
            {"name": "bounceRate"},
            {"name": "screenPageViews"},
        ],
        date_ranges=date_ranges,
        order_bys=[{"dimension": {"dimensionName": "date"}}],
        limit=400,
    )
    return {
        "rows": _parse_rows(data),
        "totals": _row_totals(data),
        "row_count": data.get("rowCount") or 0,
        "range": range_key,
        "compared": compare,
    }


async def fetch_pages(
    session: AsyncSession,
    client_id: UUID,
    *,
    range_key: str = "month",
    compare: bool = False,
    limit: int = 25,
) -> dict[str, Any]:
    """Top pages by sessions."""
    from app.routes.v1.integrations import _get_google_access_token, _get_integration_row  # noqa: PLC0415

    token = await _get_google_access_token(session, client_id, "ga4")
    row = await _get_integration_row(session, client_id, "ga4")
    extra = row.get("extra_data") or {}
    if isinstance(extra, str):
        import json
        try:
            extra = json.loads(extra)
        except Exception:
            extra = {}
    property_id = str(extra.get("selected_property") or "").strip()
    if not property_id:
        raise HTTPException(status_code=400, detail="No GA4 property selected.")

    date_ranges = _build_date_ranges(range_key, compare)

    data = await _run_report(
        token,
        property_id,
        dimensions=[{"name": "pagePath"}, {"name": "pageTitle"}],
        metrics=[
            {"name": "sessions"},
            {"name": "activeUsers"},
            {"name": "screenPageViews"},
            {"name": "averageSessionDuration"},
            {"name": "bounceRate"},
            {"name": "conversions"},
        ],
        date_ranges=date_ranges,
        order_bys=[{"metric": {"metricName": "sessions"}, "desc": True}],
        limit=limit,
    )
    return {
        "rows": _parse_rows(data),
        "totals": _row_totals(data),
        "row_count": data.get("rowCount") or 0,
    }


async def fetch_channels(
    session: AsyncSession,
    client_id: UUID,
    *,
    range_key: str = "month",
    compare: bool = False,
) -> dict[str, Any]:
    """Traffic by channel group — organic, paid, direct, referral, etc."""
    from app.routes.v1.integrations import _get_google_access_token, _get_integration_row  # noqa: PLC0415

    token = await _get_google_access_token(session, client_id, "ga4")
    row = await _get_integration_row(session, client_id, "ga4")
    extra = row.get("extra_data") or {}
    if isinstance(extra, str):
        import json
        try:
            extra = json.loads(extra)
        except Exception:
            extra = {}
    property_id = str(extra.get("selected_property") or "").strip()
    if not property_id:
        raise HTTPException(status_code=400, detail="No GA4 property selected.")

    date_ranges = _build_date_ranges(range_key, compare)

    data = await _run_report(
        token,
        property_id,
        dimensions=[{"name": "sessionDefaultChannelGrouping"}],
        metrics=[
            {"name": "sessions"},
            {"name": "activeUsers"},
            {"name": "newUsers"},
            {"name": "bounceRate"},
            {"name": "conversions"},
            {"name": "averageSessionDuration"},
        ],
        date_ranges=date_ranges,
        order_bys=[{"metric": {"metricName": "sessions"}, "desc": True}],
        limit=20,
    )
    return {
        "rows": _parse_rows(data),
        "totals": _row_totals(data),
        "row_count": data.get("rowCount") or 0,
    }


async def fetch_geo(
    session: AsyncSession,
    client_id: UUID,
    *,
    range_key: str = "month",
    compare: bool = False,
    limit: int = 30,
) -> dict[str, Any]:
    """Top cities/suburbs by sessions (city + region dimension)."""
    from app.routes.v1.integrations import _get_google_access_token, _get_integration_row  # noqa: PLC0415

    token = await _get_google_access_token(session, client_id, "ga4")
    row = await _get_integration_row(session, client_id, "ga4")
    extra = row.get("extra_data") or {}
    if isinstance(extra, str):
        import json
        try:
            extra = json.loads(extra)
        except Exception:
            extra = {}
    property_id = str(extra.get("selected_property") or "").strip()
    if not property_id:
        raise HTTPException(status_code=400, detail="No GA4 property selected.")

    date_ranges = _build_date_ranges(range_key, compare)

    data = await _run_report(
        token,
        property_id,
        dimensions=[{"name": "city"}, {"name": "region"}, {"name": "country"}],
        metrics=[
            {"name": "sessions"},
            {"name": "activeUsers"},
            {"name": "newUsers"},
            {"name": "bounceRate"},
        ],
        date_ranges=date_ranges,
        order_bys=[{"metric": {"metricName": "sessions"}, "desc": True}],
        limit=limit,
    )
    return {
        "rows": _parse_rows(data),
        "totals": _row_totals(data),
        "row_count": data.get("rowCount") or 0,
    }


async def fetch_organic_landing_pages(
    session: AsyncSession,
    client_id: UUID,
    *,
    range_key: str = "month",
    compare: bool = False,
    limit: int = 25,
) -> dict[str, Any]:
    """Top landing pages from organic search only."""
    from app.routes.v1.integrations import _get_google_access_token, _get_integration_row  # noqa: PLC0415

    token = await _get_google_access_token(session, client_id, "ga4")
    row = await _get_integration_row(session, client_id, "ga4")
    extra = row.get("extra_data") or {}
    if isinstance(extra, str):
        import json
        try:
            extra = json.loads(extra)
        except Exception:
            extra = {}
    property_id = str(extra.get("selected_property") or "").strip()
    if not property_id:
        raise HTTPException(status_code=400, detail="No GA4 property selected.")

    date_ranges = _build_date_ranges(range_key, compare)

    data = await _run_report(
        token,
        property_id,
        dimensions=[{"name": "landingPage"}, {"name": "sessionDefaultChannelGrouping"}],
        metrics=[
            {"name": "sessions"},
            {"name": "activeUsers"},
            {"name": "bounceRate"},
            {"name": "conversions"},
        ],
        date_ranges=date_ranges,
        dimension_filter={
            "filter": {
                "fieldName": "sessionDefaultChannelGrouping",
                "stringFilter": {"matchType": "CONTAINS", "value": "Organic"},
            }
        },
        order_bys=[{"metric": {"metricName": "sessions"}, "desc": True}],
        limit=limit,
    )
    return {
        "rows": _parse_rows(data),
        "totals": _row_totals(data),
        "row_count": data.get("rowCount") or 0,
    }
