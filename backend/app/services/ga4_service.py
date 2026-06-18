"""GA4 Data API v1beta — runReport wrapper for RankPilot analytics page."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

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


def resolve_period(
    range_key: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[str, str]:
    """Preset range or explicit YYYY-MM-DD bounds."""
    if start_date and end_date:
        try:
            start_d = date.fromisoformat(start_date.strip())
            end_d = date.fromisoformat(end_date.strip())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format — use YYYY-MM-DD",
            ) from exc
        if start_d > end_d:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date must be on or before end_date",
            )
        today = date.today()
        if end_d > today:
            end_d = today
        if start_d > end_d:
            start_d = end_d
        span = (end_d - start_d).days + 1
        if span > 366:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Date range cannot exceed 366 days",
            )
        return start_d.isoformat(), end_d.isoformat()
    return _date_range(range_key)


def comparison_for_period(start: str, end: str) -> tuple[str, str]:
    start_d = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    days = (end_d - start_d).days + 1
    prev_end = start_d - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    return prev_start.isoformat(), prev_end.isoformat()


def _comparison_range(range_key: str) -> tuple[str, str]:
    days = RANGE_DAYS.get(range_key, 30)
    end = date.today() - timedelta(days=days)
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def build_date_ranges(
    range_key: str,
    compare: bool,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[dict], str, str]:
    start, end = resolve_period(range_key, start_date=start_date, end_date=end_date)
    ranges = [{"startDate": start, "endDate": end, "name": "current"}]
    if compare:
        if start_date and end_date:
            cs, ce = comparison_for_period(start, end)
        else:
            cs, ce = _comparison_range(range_key)
        ranges.append({"startDate": cs, "endDate": ce, "name": "previous"})
    return ranges, start, end


def _build_date_ranges(range_key: str, compare: bool) -> list[dict]:
    ranges, _, _ = build_date_ranges(range_key, compare)
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
    metric_aggregations: list[str] | None = None,
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
    if metric_aggregations:
        body["metricAggregations"] = metric_aggregations

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

    if not r.is_success:
        # Extract the real Google error message for diagnosis
        raw_detail = r.text[:600]
        google_msg = ""
        try:
            err_obj = r.json().get("error", {})
            google_msg = str(err_obj.get("message") or "").strip()
        except Exception:
            pass

        if r.status_code == 403:
            # Identify the most common causes
            low = (google_msg or raw_detail).lower()
            if "disabled" in low or "has not been used" in low or "enable it" in low:
                detail = (
                    "Google Analytics Data API is not enabled in your Google Cloud project. "
                    "Enable it at console.cloud.google.com → APIs & Services → Library → "
                    "'Google Analytics Data API'. Then disconnect and reconnect GA4."
                )
            elif "insufficient authentication scopes" in low or "scope" in low:
                detail = (
                    "GA4 token is missing the analytics.readonly scope. "
                    "Go to Business Setup → disconnect GA4 → reconnect it to grant fresh permissions."
                )
            elif "permission" in low or "caller does not have" in low:
                detail = (
                    "Your Google account does not have access to this GA4 property. "
                    f"Google said: {google_msg or raw_detail[:200]}"
                )
            else:
                detail = (
                    f"GA4 access denied (403). "
                    f"Google said: {google_msg or raw_detail[:200]}. "
                    "Try disconnecting and reconnecting GA4 in Business Setup."
                )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

        if r.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"GA4 property not found (404). {google_msg or ''} "
                    "Reselect your GA4 property in Business Setup."
                ).strip(),
            )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GA4 API error ({r.status_code}): {google_msg or raw_detail}",
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


def _row_totals(data: dict, *, date_range_names: list[str] | None = None) -> dict[str, Any]:
    """Parse GA4 metricAggregations TOTAL rows into {current: {...}, previous: {...}}."""
    met_headers = [h["name"] for h in (data.get("metricHeaders") or [])]
    totals: dict[str, Any] = {}
    total_rows = data.get("totals") or []
    range_names = date_range_names or []

    for idx, tot_list in enumerate(total_rows):
        # GA4 returns one totals row per date range (same order as dateRanges in request).
        date_range_key: str | None = None
        for dv in tot_list.get("dimensionValues") or []:
            val = str(dv.get("value") or "").strip()
            if val and val not in {"RESERVED_TOTAL", "date_range_0", "date_range_1"}:
                date_range_key = val
                break
        if not date_range_key and idx < len(range_names):
            date_range_key = range_names[idx]
        if not date_range_key:
            date_range_key = "current" if idx == 0 else f"range_{idx}"

        vals: dict[str, Any] = {}
        for i, met in enumerate((tot_list.get("metricValues") or [])):
            key = met_headers[i] if i < len(met_headers) else f"met_{i}"
            raw = met.get("value") or "0"
            try:
                vals[key] = float(raw) if "." in raw else int(raw)
            except ValueError:
                vals[key] = raw
        totals[date_range_key] = vals
    return totals


# ── Page filter helpers ───────────────────────────────────────────────────────

def parse_page_filter(pages_param: str | list[str] | None) -> list[str]:
    if pages_param is None:
        return []
    if isinstance(pages_param, list):
        return [str(p).strip() for p in pages_param if str(p).strip()]
    return [p.strip() for p in str(pages_param).split(",") if p.strip()]


def _expand_page_urls(pages: list[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    for page in pages:
        variants = {page, page.rstrip("/"), f"{page.rstrip('/')}/"}
        for variant in variants:
            if variant and variant not in seen:
                seen.add(variant)
                expanded.append(variant)
    return expanded


def _url_to_landing_path(page_url: str) -> str:
    parsed = urlparse(page_url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return path


def build_ga4_page_location_filter(pages: list[str]) -> dict[str, Any] | None:
    if not pages:
        return None
    values = _expand_page_urls(pages)
    if len(values) == 1:
        return {
            "filter": {
                "fieldName": "pageLocation",
                "stringFilter": {"matchType": "EXACT", "value": values[0]},
            }
        }
    return {"filter": {"fieldName": "pageLocation", "inListFilter": {"values": values}}}


def build_ga4_landing_page_filter(pages: list[str]) -> dict[str, Any] | None:
    if not pages:
        return None
    paths = list(dict.fromkeys(_url_to_landing_path(p) for p in pages))
    if len(paths) == 1:
        return {
            "filter": {
                "fieldName": "landingPage",
                "stringFilter": {"matchType": "EXACT", "value": paths[0]},
            }
        }
    return {"filter": {"fieldName": "landingPage", "inListFilter": {"values": paths}}}


def combine_ga4_filters(*parts: dict[str, Any] | None) -> dict[str, Any] | None:
    expressions = [p for p in parts if p]
    if not expressions:
        return None
    if len(expressions) == 1:
        return expressions[0]
    return {"andGroup": {"expressions": expressions}}


def _filter_meta(pages: list[str] | None) -> dict[str, Any]:
    if not pages:
        return {}
    return {"filtered_pages": pages, "page_filter_active": True}


# ── High-level fetch functions ────────────────────────────────────────────────

async def fetch_overview(
    session: AsyncSession,
    client_id: UUID,
    *,
    range_key: str = "month",
    compare: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
    pages: list[str] | None = None,
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

    date_ranges, period_start, period_end = build_date_ranges(
        range_key, compare, start_date=start_date, end_date=end_date
    )

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
        dimension_filter=build_ga4_page_location_filter(pages or []),
        order_bys=[{"dimension": {"dimensionName": "date"}}],
        limit=400,
        metric_aggregations=["TOTAL"],
    )
    range_names = [str(dr.get("name") or f"range_{i}") for i, dr in enumerate(date_ranges)]
    return {
        "rows": _parse_rows(data),
        "totals": _row_totals(data, date_range_names=range_names),
        "row_count": data.get("rowCount") or 0,
        "range": "custom" if start_date and end_date else range_key,
        "compared": compare,
        "start_date": period_start,
        "end_date": period_end,
        **_filter_meta(pages),
    }


async def fetch_pages(
    session: AsyncSession,
    client_id: UUID,
    *,
    range_key: str = "month",
    compare: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 25,
    pages: list[str] | None = None,
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

    date_ranges, _, _ = build_date_ranges(
        range_key, compare, start_date=start_date, end_date=end_date
    )

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
        dimension_filter=build_ga4_page_location_filter(pages or []),
        order_bys=[{"metric": {"metricName": "sessions"}, "desc": True}],
        limit=limit,
    )
    return {
        "rows": _parse_rows(data),
        "totals": _row_totals(data),
        "row_count": data.get("rowCount") or 0,
        **_filter_meta(pages),
    }


async def fetch_channels(
    session: AsyncSession,
    client_id: UUID,
    *,
    range_key: str = "month",
    compare: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
    pages: list[str] | None = None,
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

    date_ranges, _, _ = build_date_ranges(
        range_key, compare, start_date=start_date, end_date=end_date
    )

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
        dimension_filter=build_ga4_page_location_filter(pages or []),
        order_bys=[{"metric": {"metricName": "sessions"}, "desc": True}],
        limit=20,
    )
    return {
        "rows": _parse_rows(data),
        "totals": _row_totals(data),
        "row_count": data.get("rowCount") or 0,
        **_filter_meta(pages),
    }


async def fetch_geo(
    session: AsyncSession,
    client_id: UUID,
    *,
    range_key: str = "month",
    compare: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 30,
    pages: list[str] | None = None,
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

    date_ranges, _, _ = build_date_ranges(
        range_key, compare, start_date=start_date, end_date=end_date
    )

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
        dimension_filter=build_ga4_page_location_filter(pages or []),
        order_bys=[{"metric": {"metricName": "sessions"}, "desc": True}],
        limit=limit,
    )
    return {
        "rows": _parse_rows(data),
        "totals": _row_totals(data),
        "row_count": data.get("rowCount") or 0,
        **_filter_meta(pages),
    }


async def fetch_organic_landing_pages(
    session: AsyncSession,
    client_id: UUID,
    *,
    range_key: str = "month",
    compare: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 25,
    pages: list[str] | None = None,
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

    date_ranges, _, _ = build_date_ranges(
        range_key, compare, start_date=start_date, end_date=end_date
    )

    organic_filter = {
        "filter": {
            "fieldName": "sessionDefaultChannelGrouping",
            "stringFilter": {"matchType": "CONTAINS", "value": "Organic"},
        }
    }
    page_filter = build_ga4_landing_page_filter(pages or [])

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
        dimension_filter=combine_ga4_filters(organic_filter, page_filter),
        order_bys=[{"metric": {"metricName": "sessions"}, "desc": True}],
        limit=limit,
    )
    return {
        "rows": _parse_rows(data),
        "totals": _row_totals(data),
        "row_count": data.get("rowCount") or 0,
        **_filter_meta(pages),
    }


def _gsc_site_to_base_url(site: str) -> str:
    site = (site or "").strip()
    if not site:
        return ""
    if site.startswith("sc-domain:"):
        return f"https://{site.removeprefix('sc-domain:').strip()}"
    if site.startswith("http://") or site.startswith("https://"):
        return site.rstrip("/")
    return ""


def _ga4_path_to_url(base_url: str, path: str) -> str:
    path = (path or "/").strip()
    if not path.startswith("/"):
        path = f"/{path}"
    if base_url:
        return f"{base_url.rstrip('/')}{path}"
    return path


def _title_from_path(path: str) -> str:
    slug = path.strip("/").split("/")[-1] if path.strip("/") else path
    title = slug.replace("-", " ").replace("_", " ").strip()
    return title.title() if title else path


async def _client_site_base_url(session: AsyncSession, client_id: UUID) -> str:
    try:
        from app.services.gsc_service import _gsc_site_url  # noqa: PLC0415

        base = _gsc_site_to_base_url(await _gsc_site_url(session, client_id))
        if base:
            return base
    except Exception:
        pass

    from sqlalchemy import text  # noqa: PLC0415

    row = (
        await session.execute(
            text("SELECT business_url FROM rp_clients WHERE client_id = :cid LIMIT 1"),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    if row:
        return _gsc_site_to_base_url(str(row.get("business_url") or ""))
    return ""


async def fetch_page_options(
    session: AsyncSession,
    client_id: UUID,
    *,
    range_key: str = "month",
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Merged page list for the dashboard page selector — GSC URLs + GA4 paths."""
    from app.services.gsc_service import fetch_gsc_top_pages  # noqa: PLC0415

    start, end = resolve_period(range_key, start_date=start_date, end_date=end_date)
    custom = bool(start_date and end_date)
    base_url = await _client_site_base_url(session, client_id)
    by_key: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    try:
        gsc_data = await fetch_gsc_top_pages(
            session,
            client_id,
            range_key=range_key,
            start_date=start_date,
            end_date=end_date,
            limit=min(limit, 250),
        )
        for row in gsc_data.get("rows") or []:
            page = str(row.get("page") or "").strip()
            if not page:
                continue
            key = page.rstrip("/")
            by_key[key] = {
                "page": page,
                "title": _title_from_path(urlparse(page).path or "/"),
                "clicks": int(row.get("clicks") or 0),
                "sessions": 0,
                "source": "gsc",
            }
    except HTTPException as exc:
        warnings.append(str(exc.detail))
    except Exception as exc:
        logger.warning("GSC page options failed: %s", exc)
        warnings.append("Search Console pages could not be loaded.")

    try:
        ga4_data = await fetch_pages(
            session,
            client_id,
            range_key=range_key,
            start_date=start_date,
            end_date=end_date,
            limit=min(limit, 100),
        )
        for row in ga4_data.get("rows") or []:
            path = str(row.get("pagePath") or "").strip()
            if not path:
                continue
            page = _ga4_path_to_url(base_url, path)
            key = page.rstrip("/")
            sessions = int(row.get("sessions") or 0)
            title = str(row.get("pageTitle") or "").strip() or _title_from_path(path)
            existing = by_key.get(key)
            if existing:
                existing["sessions"] = sessions
                existing["source"] = "both"
                if title:
                    existing["title"] = title
            else:
                by_key[key] = {
                    "page": page,
                    "title": title,
                    "clicks": 0,
                    "sessions": sessions,
                    "source": "ga4",
                }
    except HTTPException as exc:
        warnings.append(str(exc.detail))
    except Exception as exc:
        logger.warning("GA4 page options failed: %s", exc)
        warnings.append("GA4 pages could not be loaded.")

    rows = sorted(
        by_key.values(),
        key=lambda r: (int(r.get("clicks") or 0), int(r.get("sessions") or 0)),
        reverse=True,
    )[:limit]

    return {
        "rows": rows,
        "row_count": len(rows),
        "range": "custom" if custom else range_key,
        "start_date": start,
        "end_date": end,
        "site_base_url": base_url or None,
        "warnings": warnings,
    }
