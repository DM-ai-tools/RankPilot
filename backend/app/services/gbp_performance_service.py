"""Google Business Profile Performance API — calls, clicks, directions, daily trend."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ga4_service import _comparison_range, comparison_for_period, resolve_period

logger = logging.getLogger(__name__)

_GBP_PERF_URL = "https://businessprofileperformance.googleapis.com/v1/{location}:fetchMultiDailyMetricsTimeSeries"

_DAILY_METRICS = [
    "CALL_CLICKS",
    "WEBSITE_CLICKS",
    "BUSINESS_DIRECTION_REQUESTS",
    "BUSINESS_CONVERSATIONS",
    "BUSINESS_BOOKINGS",
    "BUSINESS_FOOD_MENU_CLICKS",
]

_METRIC_KEY = {
    "CALL_CLICKS": "calls",
    "WEBSITE_CLICKS": "website_clicks",
    "BUSINESS_DIRECTION_REQUESTS": "directions",
    "BUSINESS_CONVERSATIONS": "messages",
    "BUSINESS_BOOKINGS": "bookings",
    "BUSINESS_FOOD_MENU_CLICKS": "menus",
}


async def _gbp_location_name(session: AsyncSession, client_id: UUID) -> str:
    from app.routes.v1.integrations import _get_integration_row  # noqa: PLC0415

    row = await _get_integration_row(session, client_id, "gbp")
    extra = row.get("extra_data") or {}
    if isinstance(extra, str):
        import json

        try:
            extra = json.loads(extra)
        except Exception:
            extra = {}
    loc = str(extra.get("selected_property") or "").strip()
    if not loc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Google Business Profile location selected. Choose one in Business Setup.",
        )
    if not loc.startswith("locations/"):
        loc = f"locations/{loc}"
    return loc


def _date_query_params(prefix: str, d: date) -> list[tuple[str, str]]:
    return [
        (f"{prefix}.year", str(d.year)),
        (f"{prefix}.month", str(d.month)),
        (f"{prefix}.day", str(d.day)),
    ]


def _iso_from_dated(dated: dict) -> str:
    d = dated.get("date") or {}
    try:
        return date(int(d["year"]), int(d["month"]), int(d["day"])).isoformat()
    except (KeyError, TypeError, ValueError):
        return ""


def _parse_gbp_time_series(payload: dict) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Merge per-metric daily series into rows + period totals."""
    by_date: dict[str, dict[str, int]] = {}
    totals = {v: 0 for v in _METRIC_KEY.values()}

    for block in payload.get("multiDailyMetricTimeSeries") or []:
        for series in block.get("dailyMetricTimeSeries") or []:
            metric = str(series.get("dailyMetric") or "")
            key = _METRIC_KEY.get(metric)
            if not key:
                continue
            dated_values = ((series.get("timeSeries") or {}).get("datedValues") or [])
            for dv in dated_values:
                iso = _iso_from_dated(dv)
                if not iso:
                    continue
                val = int(str(dv.get("value") or "0"))
                row = by_date.setdefault(
                    iso,
                    {k: 0 for k in _METRIC_KEY.values()},
                )
                row[key] += val
                totals[key] += val

    rows: list[dict[str, Any]] = []
    for iso in sorted(by_date.keys()):
        m = by_date[iso]
        interactions = m["calls"] + m["website_clicks"] + m["directions"]
        rows.append({"date": iso, "interactions": interactions, **m})

    period_interactions = totals["calls"] + totals["website_clicks"] + totals["directions"]
    totals_out = {"interactions": period_interactions, **totals}
    return rows, totals_out


async def _fetch_gbp_metrics(
    token: str,
    location: str,
    *,
    start: str,
    end: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    sd = date.fromisoformat(start)
    ed = date.fromisoformat(end)
    params: list[tuple[str, str]] = []
    for m in _DAILY_METRICS:
        params.append(("dailyMetrics", m))
    params.extend(_date_query_params("dailyRange.startDate", sd))
    params.extend(_date_query_params("dailyRange.endDate", ed))

    url = _GBP_PERF_URL.format(location=location)
    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            r = await http.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GBP Performance API request failed: {exc}",
        ) from exc

    if not r.is_success:
        google_msg = ""
        try:
            google_msg = str(r.json().get("error", {}).get("message") or "").strip()
        except Exception:
            google_msg = r.text[:300]
        if r.status_code == 403:
            low = google_msg.lower()
            if "disabled" in low or "not been used" in low:
                detail = (
                    "Business Profile Performance API is not enabled in Google Cloud. "
                    "Enable businessprofileperformance.googleapis.com, then reconnect GBP."
                )
            else:
                detail = f"GBP access denied: {google_msg or 'reconnect GBP in Business Setup.'}"
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GBP Performance API error ({r.status_code}): {google_msg or r.text[:200]}",
        )

    return _parse_gbp_time_series(r.json())


async def fetch_gbp_performance(
    session: AsyncSession,
    client_id: UUID,
    *,
    range_key: str = "month",
    compare: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """GBP overview — interactions, calls, website clicks, directions + daily trend."""
    from app.routes.v1.integrations import _get_google_access_token  # noqa: PLC0415

    token = await _get_google_access_token(session, client_id, "gbp")
    location = await _gbp_location_name(session, client_id)
    start, end = resolve_period(range_key, start_date=start_date, end_date=end_date)
    custom = bool(start_date and end_date)

    rows, totals = await _fetch_gbp_metrics(token, location, start=start, end=end)

    result: dict[str, Any] = {
        "totals": totals,
        "rows": rows,
        "row_count": len(rows),
        "range": "custom" if custom else range_key,
        "compared": compare,
        "location": location,
        "start_date": start,
        "end_date": end,
    }

    if compare:
        if custom:
            p_start, p_end = comparison_for_period(start, end)
        else:
            p_start, p_end = _comparison_range(range_key)
        _, prev_totals = await _fetch_gbp_metrics(token, location, start=p_start, end=p_end)
        result["prev_totals"] = prev_totals

    return result
