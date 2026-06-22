"""Google Search Console — search analytics (queries, clicks, impressions, position)."""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote, unquote, urlparse
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_ahrefs_api_key, get_settings
from app.services.ahrefs_service import AhrefsClient, format_volume_display
from app.services.ga4_service import (
    _comparison_range,
    comparison_for_period,
    resolve_period,
)
logger = logging.getLogger(__name__)

_GSC_QUERY_URL = "https://www.googleapis.com/webmasters/v3/sites/{site_url}/searchAnalytics/query"


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


async def _gsc_site_url(session: AsyncSession, client_id: UUID) -> str:
    from app.routes.v1.integrations import _get_integration_row  # noqa: PLC0415

    row = await _get_integration_row(session, client_id, "gsc")
    extra = row.get("extra_data") or {}
    if isinstance(extra, str):
        import json

        try:
            extra = json.loads(extra)
        except Exception:
            extra = {}
    site = str(extra.get("selected_property") or "").strip()
    if not site:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Search Console property selected. Choose one in Business Setup.",
        )
    return site


def _build_gsc_page_filter_groups(pages: list[str]) -> list[dict[str, Any]] | None:
    """GSC only supports AND within a filter group; OR is not supported by the API."""
    if not pages:
        return None
    if len(pages) != 1:
        return None
    return [{"filters": [{"dimension": "page", "operator": "equals", "expression": pages[0]}]}]


def _merge_gsc_rows(rows_list: list[list[dict[str, Any]]], dimensions: list[str] | None) -> list[dict[str, Any]]:
    dims = dimensions or []
    merged: dict[tuple[str, ...], dict[str, Any]] = {}

    for rows in rows_list:
        for row in rows:
            key = tuple(str(row.get(d) or "") for d in dims) if dims else ("__total__",)
            existing = merged.get(key)
            if not existing:
                merged[key] = dict(row)
                continue
            old_clicks = int(existing.get("clicks") or 0)
            new_clicks = int(row.get("clicks") or 0)
            total_clicks = old_clicks + new_clicks
            old_impr = int(existing.get("impressions") or 0)
            new_impr = int(row.get("impressions") or 0)
            total_impr = old_impr + new_impr
            if total_clicks > 0:
                existing["position"] = (
                    float(existing.get("position") or 0) * old_clicks
                    + float(row.get("position") or 0) * new_clicks
                ) / total_clicks
            existing["clicks"] = total_clicks
            existing["impressions"] = total_impr
            existing["ctr"] = total_clicks / total_impr if total_impr else 0.0

    return list(merged.values())


async def _gsc_run_query_once(
    token: str,
    site_url: str,
    *,
    start_date: str,
    end_date: str,
    dimensions: list[str] | None = None,
    limit: int = 250,
    pages: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Run a Search Console searchAnalytics query."""
    encoded_site = quote(site_url, safe="")
    url = _GSC_QUERY_URL.format(site_url=encoded_site)
    body: dict[str, Any] = {
        "startDate": start_date,
        "endDate": end_date,
        "rowLimit": min(limit, 25_000),
        "startRow": 0,
    }
    if dimensions:
        body["dimensions"] = dimensions
    page_filters = _build_gsc_page_filter_groups(pages or [])
    if page_filters:
        body["dimensionFilterGroups"] = page_filters

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
            detail=f"Search Console API request failed: {exc}",
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
                    "Google Search Console API is not enabled in your Google Cloud project. "
                    "Enable it at console.cloud.google.com → APIs & Services → Library → "
                    "'Google Search Console API', then reconnect GSC in Business Setup."
                )
            else:
                detail = f"Search Console access denied: {google_msg or 'reconnect GSC in Business Setup.'}"
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Search Console API error ({r.status_code}): {google_msg or r.text[:200]}",
        )

    out: list[dict[str, Any]] = []
    dims = dimensions or []
    for row in (r.json().get("rows") or []):
        keys = row.get("keys") or []
        record: dict[str, Any] = {
            "clicks": int(row.get("clicks") or 0),
            "impressions": int(row.get("impressions") or 0),
            "ctr": float(row.get("ctr") or 0),
            "position": float(row.get("position") or 0),
        }
        for i, dim in enumerate(dims):
            record[dim] = str(keys[i] if i < len(keys) else "")
        out.append(record)
    return out


def _page_url_variants(url: str) -> list[str]:
    variants = [url]
    alt = url.rstrip("/") if url.endswith("/") else f"{url}/"
    if alt and alt not in variants:
        variants.append(alt)
    return variants


async def _gsc_run_query(
    token: str,
    site_url: str,
    *,
    start_date: str,
    end_date: str,
    dimensions: list[str] | None = None,
    limit: int = 250,
    pages: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Run GSC query; for multiple pages, query each page and merge (GSC has no OR filter)."""
    if pages and len(pages) > 1:
        per_page = [
            await _gsc_run_query_once(
                token,
                site_url,
                start_date=start_date,
                end_date=end_date,
                dimensions=dimensions,
                limit=limit,
                pages=[page],
            )
            for page in pages
        ]
        return _merge_gsc_rows(per_page, dimensions)

    if pages and len(pages) == 1:
        variants = _page_url_variants(pages[0])
        if len(variants) > 1:
            per_variant = [
                await _gsc_run_query_once(
                    token,
                    site_url,
                    start_date=start_date,
                    end_date=end_date,
                    dimensions=dimensions,
                    limit=limit,
                    pages=[variant],
                )
                for variant in variants
            ]
            return _merge_gsc_rows(per_variant, dimensions)

    return await _gsc_run_query_once(
        token,
        site_url,
        start_date=start_date,
        end_date=end_date,
        dimensions=dimensions,
        limit=limit,
        pages=pages,
    )


def _gsc_filter_meta(pages: list[str] | None) -> dict[str, Any]:
    if not pages:
        return {}
    return {"filtered_pages": pages, "page_filter_active": True}


async def _gsc_search_queries(
    token: str,
    site_url: str,
    *,
    start_date: str,
    end_date: str,
    limit: int = 50,
    pages: list[str] | None = None,
) -> list[dict[str, Any]]:
    rows = await _gsc_run_query(
        token,
        site_url,
        start_date=start_date,
        end_date=end_date,
        dimensions=["query"],
        limit=limit,
        pages=pages,
    )
    return [
        {
            "keyword": str(r.get("query") or "").strip(),
            "clicks": r["clicks"],
            "impressions": r["impressions"],
            "ctr": r["ctr"],
            "position": r["position"],
        }
        for r in rows
        if str(r.get("query") or "").strip()
    ]


async def _attach_ahrefs_volumes(
    session: AsyncSession,
    rows: list[dict[str, Any]],
    *,
    client_id: UUID,
) -> tuple[list[dict[str, Any]], str]:
    if not rows or not get_ahrefs_api_key():
        return rows, "none"

    profile = (
        await session.execute(
            text("SELECT metro_label FROM rp_clients WHERE client_id = :cid LIMIT 1"),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    metro = str((profile or {}).get("metro_label") or "")
    country = _country_for_metro(metro)

    keywords = [str(r["keyword"]) for r in rows if r.get("keyword")]
    client = AhrefsClient(get_settings())
    try:
        ahrefs_rows = await client.keywords_overview(keywords, country=country)
    except Exception as exc:
        logger.warning("Ahrefs volume lookup for GSC keywords failed: %s", exc)
        return rows, "ahrefs_error"
    finally:
        await client.aclose()

    by_kw = {str(r.get("keyword") or "").lower(): r for r in ahrefs_rows if r.get("keyword")}
    enriched: list[dict[str, Any]] = []
    for row in rows:
        kw = str(row["keyword"])
        ah = by_kw.get(kw.lower(), {})
        volume = int(ah.get("volume") or 0)
        enriched.append(
            {
                **row,
                "volume": volume,
                "volume_display": format_volume_display(volume, global_volume=ah.get("global_volume")),
                "difficulty": ah.get("difficulty"),
                "traffic_potential": ah.get("traffic_potential"),
            }
        )
    return enriched, "ahrefs"


def _gsc_totals_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}
    row = rows[0]
    return {
        "clicks": int(row.get("clicks") or 0),
        "impressions": int(row.get("impressions") or 0),
        "ctr": float(row.get("ctr") or 0),
        "position": float(row.get("position") or 0),
    }


def _previous_period(
    start: str,
    end: str,
    range_key: str,
    *,
    custom: bool,
) -> tuple[str, str]:
    if custom:
        return comparison_for_period(start, end)
    return _comparison_range(range_key)


async def fetch_gsc_performance(
    session: AsyncSession,
    client_id: UUID,
    *,
    range_key: str = "month",
    compare: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
    pages: list[str] | None = None,
) -> dict[str, Any]:
    """GSC search performance — daily clicks/impressions trend + period totals."""
    from app.routes.v1.integrations import _get_google_access_token  # noqa: PLC0415

    token = await _get_google_access_token(session, client_id, "gsc")
    site_url = await _gsc_site_url(session, client_id)

    start, end = resolve_period(range_key, start_date=start_date, end_date=end_date)
    custom = bool(start_date and end_date)
    totals_rows = await _gsc_run_query(
        token, site_url, start_date=start, end_date=end, dimensions=None, limit=1, pages=pages
    )
    daily_rows = await _gsc_run_query(
        token,
        site_url,
        start_date=start,
        end_date=end,
        dimensions=["date"],
        limit=25_000,
        pages=pages,
    )
    daily_rows.sort(key=lambda r: str(r.get("date") or ""))

    result: dict[str, Any] = {
        "totals": _gsc_totals_row(totals_rows),
        "rows": daily_rows,
        "row_count": len(daily_rows),
        "range": "custom" if custom else range_key,
        "compared": compare,
        "gsc_site": site_url,
        "start_date": start,
        "end_date": end,
        **_gsc_filter_meta(pages),
    }

    if compare:
        p_start, p_end = _previous_period(start, end, range_key, custom=custom)
        prev_totals_rows = await _gsc_run_query(
            token,
            site_url,
            start_date=p_start,
            end_date=p_end,
            dimensions=None,
            limit=1,
            pages=pages,
        )
        result["prev_totals"] = _gsc_totals_row(prev_totals_rows)

    return result


async def _gsc_search_pages(
    token: str,
    site_url: str,
    *,
    start_date: str,
    end_date: str,
    limit: int = 250,
    pages: list[str] | None = None,
) -> list[dict[str, Any]]:
    rows = await _gsc_run_query(
        token,
        site_url,
        start_date=start_date,
        end_date=end_date,
        dimensions=["page"],
        limit=limit,
        pages=pages,
    )
    return [
        {
            "page": str(r.get("page") or "").strip(),
            "clicks": r["clicks"],
            "impressions": r["impressions"],
            "ctr": r["ctr"],
            "position": r["position"],
        }
        for r in rows
        if str(r.get("page") or "").strip()
    ]


def _page_title_from_url(page_url: str) -> str:
    try:
        parsed = urlparse(page_url)
        path = (parsed.path or "").strip("/")
        if not path:
            return parsed.netloc or page_url
        slug = unquote(path.split("/")[-1])
        title = slug.replace("-", " ").replace("_", " ").strip()
        return title.title() if title else page_url
    except Exception:
        return page_url


def _merge_gsc_page_periods(
    curr_rows: list[dict[str, Any]],
    prev_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    curr_by = {str(r["page"]): r for r in curr_rows}
    prev_by = {str(r["page"]): r for r in prev_rows}
    merged: list[dict[str, Any]] = []

    for page in curr_by.keys() | prev_by.keys():
        curr = curr_by.get(page, {})
        prev = prev_by.get(page, {})
        clicks = int(curr.get("clicks") or 0)
        prev_clicks = int(prev.get("clicks") or 0)
        delta = clicks - prev_clicks
        if prev_clicks > 0:
            change_pct = round((delta / prev_clicks) * 100, 1)
        elif clicks > 0:
            change_pct = None
        else:
            change_pct = 0.0

        merged.append(
            {
                "page": page,
                "title": _page_title_from_url(page),
                "clicks": clicks,
                "prev_clicks": prev_clicks,
                "change_clicks": delta,
                "change_pct": change_pct,
                "impressions": int(curr.get("impressions") or 0),
                "ctr": float(curr.get("ctr") or 0),
                "position": float(curr.get("position") or 0),
            }
        )
    return merged


async def fetch_gsc_content_insights(
    session: AsyncSession,
    client_id: UUID,
    *,
    range_key: str = "month",
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 20,
    pages: list[str] | None = None,
) -> dict[str, Any]:
    """GSC content insights — top pages, trending up, and trending down vs previous period."""
    from app.routes.v1.integrations import _get_google_access_token  # noqa: PLC0415

    token = await _get_google_access_token(session, client_id, "gsc")
    site_url = await _gsc_site_url(session, client_id)

    start, end = resolve_period(range_key, start_date=start_date, end_date=end_date)
    custom = bool(start_date and end_date)
    p_start, p_end = _previous_period(start, end, range_key, custom=custom)

    pool_limit = max(limit * 10, 250)
    curr_rows = await _gsc_search_pages(
        token, site_url, start_date=start, end_date=end, limit=pool_limit, pages=pages
    )
    prev_rows = await _gsc_search_pages(
        token, site_url, start_date=p_start, end_date=p_end, limit=pool_limit, pages=pages
    )
    merged = _merge_gsc_page_periods(curr_rows, prev_rows)

    top = sorted(merged, key=lambda r: r["clicks"], reverse=True)[:limit]

    trending_up = [r for r in merged if r["clicks"] > r["prev_clicks"]]
    trending_up.sort(
        key=lambda r: (
            r["change_pct"] if r["change_pct"] is not None else 10_000 + r["clicks"],
        ),
        reverse=True,
    )
    trending_up = trending_up[:limit]

    trending_down = [r for r in merged if r["clicks"] < r["prev_clicks"] and r["prev_clicks"] > 0]
    trending_down.sort(key=lambda r: r["change_pct"] if r["change_pct"] is not None else 0)
    trending_down = trending_down[:limit]

    return {
        "top": top,
        "trending_up": trending_up,
        "trending_down": trending_down,
        "range": "custom" if custom else range_key,
        "gsc_site": site_url,
        "start_date": start,
        "end_date": end,
        "prev_start_date": p_start,
        "prev_end_date": p_end,
        **_gsc_filter_meta(pages),
    }


async def fetch_gsc_top_pages(
    session: AsyncSession,
    client_id: UUID,
    *,
    range_key: str = "month",
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 25,
    pages: list[str] | None = None,
) -> dict[str, Any]:
    """GSC top pages by clicks — page URL, clicks, impressions, CTR, position."""
    from app.routes.v1.integrations import _get_google_access_token  # noqa: PLC0415

    token = await _get_google_access_token(session, client_id, "gsc")
    site_url = await _gsc_site_url(session, client_id)

    start, end = resolve_period(range_key, start_date=start_date, end_date=end_date)
    custom = bool(start_date and end_date)
    rows = await _gsc_search_pages(
        token, site_url, start_date=start, end_date=end, limit=limit, pages=pages
    )

    return {
        "rows": rows,
        "row_count": len(rows),
        "range": "custom" if custom else range_key,
        "gsc_site": site_url,
        "start_date": start,
        "end_date": end,
        **_gsc_filter_meta(pages),
    }


async def fetch_gsc_keywords(
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
    """Top GSC search queries with Ahrefs monthly search volume."""
    from app.routes.v1.integrations import _get_google_access_token  # noqa: PLC0415

    token = await _get_google_access_token(session, client_id, "gsc")
    site_url = await _gsc_site_url(session, client_id)

    start, end = resolve_period(range_key, start_date=start_date, end_date=end_date)
    custom = bool(start_date and end_date)
    rows = await _gsc_search_queries(token, site_url, start_date=start, end_date=end, limit=limit, pages=pages)
    rows, volume_source = await _attach_ahrefs_volumes(session, rows, client_id=client_id)

    prev_by_kw: dict[str, dict[str, Any]] = {}
    if compare:
        p_start, p_end = _previous_period(start, end, range_key, custom=custom)
        prev_rows = await _gsc_search_queries(
            token, site_url, start_date=p_start, end_date=p_end, limit=limit, pages=pages
        )
        prev_by_kw = {str(r["keyword"]).lower(): r for r in prev_rows}

    if compare and prev_by_kw:
        for row in rows:
            prev = prev_by_kw.get(str(row["keyword"]).lower())
            if prev:
                row["prev_clicks"] = prev.get("clicks", 0)
                row["prev_impressions"] = prev.get("impressions", 0)
                row["prev_position"] = prev.get("position", 0)

    return {
        "rows": rows,
        "row_count": len(rows),
        "range": "custom" if custom else range_key,
        "compared": compare,
        "gsc_site": site_url,
        "volume_source": volume_source,
        "start_date": start,
        "end_date": end,
        **_gsc_filter_meta(pages),
    }


def _normalize_kw_text(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip().lower())


def _keyword_matches(candidate: str, query: str) -> bool:
    """Exact or same-word-set match for GSC query rows."""
    cand = _normalize_kw_text(candidate)
    q = _normalize_kw_text(query)
    if not cand or not q:
        return False
    if cand == q:
        return True
    cand_words = set(cand.split())
    query_words = set(q.split())
    return cand_words == query_words or cand_words <= query_words or query_words <= cand_words


def _build_gsc_page_contains_filter(path: str) -> list[dict[str, Any]]:
    expr = path if path.startswith("/") else f"/{path}"
    return [{"filters": [{"dimension": "page", "operator": "contains", "expression": expr}]}]


async def _gsc_run_query_page_contains(
    token: str,
    site_url: str,
    *,
    path: str,
    start_date: str,
    end_date: str,
    dimensions: list[str] | None = None,
    limit: int = 2500,
) -> list[dict[str, Any]]:
    """Query GSC rows where page URL contains the path (trailing-slash tolerant)."""
    encoded_site = quote(site_url, safe="")
    url = _GSC_QUERY_URL.format(site_url=encoded_site)
    body: dict[str, Any] = {
        "startDate": start_date,
        "endDate": end_date,
        "rowLimit": min(limit, 25_000),
        "startRow": 0,
        "dimensionFilterGroups": _build_gsc_page_contains_filter(path),
    }
    if dimensions:
        body["dimensions"] = dimensions
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
            detail=f"Search Console API request failed: {exc}",
        ) from exc
    if not r.is_success:
        return []
    out: list[dict[str, Any]] = []
    dims = dimensions or []
    for row in (r.json().get("rows") or []):
        keys = row.get("keys") or []
        record: dict[str, Any] = {
            "clicks": int(row.get("clicks") or 0),
            "impressions": int(row.get("impressions") or 0),
            "ctr": float(row.get("ctr") or 0),
            "position": float(row.get("position") or 0),
        }
        for i, dim in enumerate(dims):
            record[dim] = str(keys[i] if i < len(keys) else "")
        out.append(record)
    return out


async def fetch_gsc_keyword_position(
    session: AsyncSession,
    client_id: UUID,
    *,
    keyword: str,
    page_url: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any] | None:
    """Average Google Search position for a query (optional published page URL filter)."""
    keyword = (keyword or "").strip()
    if not keyword:
        return None
    try:
        from app.routes.v1.integrations import _get_google_access_token  # noqa: PLC0415

        token = await _get_google_access_token(session, client_id, "gsc")
        site_url = await _gsc_site_url(session, client_id)
    except HTTPException:
        return None
    except Exception:
        logger.warning("GSC keyword position setup failed", exc_info=True)
        return None

    end = end_date or date.today()
    start = start_date or (end - timedelta(days=6))
    dimensions = ["query", "page"] if page_url else ["query"]

    try:
        rows = await _gsc_run_query(
            token,
            site_url,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            dimensions=dimensions,
            pages=[page_url] if page_url else None,
            limit=2500,
        )
    except HTTPException:
        return None

    kw_low = _normalize_kw_text(keyword)
    best: dict[str, Any] | None = None

    def _consider_row(row: dict[str, Any]) -> None:
        nonlocal best
        q = str(row.get("query") or "").strip()
        if not _keyword_matches(keyword, q):
            return
        impressions = int(row.get("impressions") or 0)
        if impressions <= 0:
            return
        pos = float(row.get("position") or 0)
        if pos <= 0:
            return
        rounded = max(1, int(round(pos)))
        if best is None or rounded < int(best["organic_position"]):
            best = {
                "position": round(pos, 1),
                "organic_position": rounded,
                "impressions": impressions,
                "clicks": int(row.get("clicks") or 0),
                "source": "gsc",
                "matched_query": q,
            }

    for row in rows:
        _consider_row(row)

    # Page filter + exact keyword often misses — scan all queries for this URL.
    if best is None and page_url:
        try:
            page_rows = await _gsc_run_query(
                token,
                site_url,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                dimensions=["query"],
                pages=[page_url],
                limit=2500,
            )
        except HTTPException:
            page_rows = []
        for row in page_rows:
            _consider_row(row)

        if best is None and page_url:
            path = urlparse(page_url).path.rstrip("/").lower()
            if path:
                try:
                    contains_rows = await _gsc_run_query_page_contains(
                        token,
                        site_url,
                        path=path,
                        start_date=start.isoformat(),
                        end_date=end.isoformat(),
                        dimensions=["query", "page"],
                    )
                except HTTPException:
                    contains_rows = []
                for row in contains_rows:
                    _consider_row(row)

    return best
