"""Monthly SEO reports — built from rank history, content queue, and citations."""

from __future__ import annotations

import calendar
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.lib.visibility_scoring import count_rank_bands, visibility_score_pct

logger = logging.getLogger(__name__)


async def _client_profile_brief(session: AsyncSession, client_id: UUID) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT business_name, primary_keyword, metro_label
                FROM rp_clients WHERE client_id = :cid
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        return {"business_name": "", "primary_keyword": "", "metro_label": ""}
    return {
        "business_name": str(row.get("business_name") or ""),
        "primary_keyword": str(row.get("primary_keyword") or ""),
        "metro_label": str(row.get("metro_label") or ""),
    }


async def _client_keyword(session: AsyncSession, client_id: UUID) -> str:
    prof = await _client_profile_brief(session, client_id)
    return prof["primary_keyword"]


async def _months_with_activity(session: AsyncSession, client_id: UUID, limit: int = 12) -> list[datetime]:
    rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT month_start
                FROM (
                  SELECT date_trunc('month', checked_at)::date AS month_start
                  FROM rp_rank_history
                  WHERE client_id = :cid
                  UNION
                  SELECT date_trunc('month', COALESCE(published_at, created_at))::date AS month_start
                  FROM rp_content_queue
                  WHERE client_id = :cid
                ) m
                WHERE month_start IS NOT NULL
                ORDER BY month_start DESC
                LIMIT :lim
                """
            ),
            {"cid": str(client_id), "lim": limit},
        )
    ).mappings().all()
    out: list[datetime] = []
    for r in rows:
        ms = r.get("month_start")
        if ms is None:
            continue
        if hasattr(ms, "year"):
            out.append(datetime(ms.year, ms.month, 1, tzinfo=UTC))
        elif isinstance(ms, datetime):
            out.append(ms.replace(day=1, tzinfo=UTC) if ms.tzinfo is None else ms.replace(day=1))
    return out


async def _rank_rows_as_of(
    session: AsyncSession,
    client_id: UUID,
    keyword: str,
    as_of: datetime,
) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT ON (s.id)
                  s.population,
                  r.rank_position
                FROM rp_suburb_grid s
                LEFT JOIN rp_rank_history r
                  ON r.suburb_id = s.id
                 AND r.client_id = :cid
                 AND LOWER(TRIM(r.keyword)) = LOWER(TRIM(:kw))
                 AND r.checked_at < :as_of
                WHERE s.client_id = :cid
                ORDER BY s.id, r.checked_at DESC NULLS LAST
                """
            ),
            {"cid": str(client_id), "kw": keyword, "as_of": as_of},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def _month_end(month_start: datetime) -> datetime:
    y, m = month_start.year, month_start.month
    last_day = calendar.monthrange(y, m)[1]
    return datetime(y, m, last_day, 23, 59, 59, tzinfo=UTC)


def _pdf_api_path(month_yyyy_mm: str) -> str:
    return f"/api/v1/reports/monthly/{month_yyyy_mm}/pdf"


def _parse_report_month(month: str) -> datetime:
    """Parse YYYY-MM or YYYY-MM-DD to month start UTC."""
    raw = (month or "").strip()[:10]
    if len(raw) < 7:
        raise ValueError("Invalid month")
    y, m = int(raw[:4]), int(raw[5:7])
    return datetime(y, m, 1, tzinfo=UTC)


async def get_monthly_report(
    session: AsyncSession,
    client_id: UUID,
    month: str,
) -> dict | None:
    """Build one report for YYYY-MM if that month has activity."""
    try:
        month_start = _parse_report_month(month)
    except (ValueError, TypeError):
        return None
    months = await _months_with_activity(session, client_id, limit=24)
    if not any(ms.year == month_start.year and ms.month == month_start.month for ms in months):
        return None
    keyword = await _client_keyword(session, client_id)
    report = await build_monthly_report(session, client_id, month_start, keyword)
    report["pdf_url"] = _pdf_api_path(month_start.strftime("%Y-%m"))
    return report


async def generate_monthly_report_pdf(
    session: AsyncSession,
    client_id: UUID,
    month: str,
) -> tuple[bytes, str]:
    """Return (pdf_bytes, filename)."""
    from app.lib.report_pdf import render_monthly_report_pdf

    report = await get_monthly_report(session, client_id, month)
    if not report:
        raise ValueError("No report for this month")

    prof = await _client_profile_brief(session, client_id)
    month_label = datetime.fromisoformat(report["month"] + "T00:00:00").strftime("%B %Y")
    pdf = render_monthly_report_pdf(
        business_name=prof["business_name"],
        month_label=month_label,
        keyword=prof["primary_keyword"],
        report={**report, "gbp_posts": report.get("gbp_posts")},
    )
    safe_name = (prof["business_name"] or "report").replace(" ", "-")[:40]
    filename = f"RankPilot-SEO-{safe_name}-{report['month'][:7]}.pdf"
    return pdf, filename


def _report_id(client_id: UUID, month_start: datetime) -> str:
    return f"{client_id}-{month_start.strftime('%Y-%m')}"


def _build_narrative(
    *,
    month_label: str,
    keyword: str,
    vis_start: float | None,
    vis_end: float | None,
    top3_start: int | None,
    top3_end: int | None,
    pages_published: int,
    citations_ok: int,
    gbp_posts: int,
    in_progress: bool,
) -> str:
    parts = [f"Monthly SEO summary for {month_label}."]
    if vis_start is not None and vis_end is not None:
        delta = round(vis_end - vis_start, 1)
        sign = "+" if delta >= 0 else ""
        parts.append(
            f"Maps visibility for “{keyword}” moved from {vis_start}% to {vis_end}% ({sign}{delta} pts)."
        )
    elif vis_end is not None:
        parts.append(f"Maps visibility score ended at {vis_end}% for “{keyword}”.")
    if top3_start is not None and top3_end is not None and top3_start != top3_end:
        parts.append(f"Top-3 suburbs changed from {top3_start} to {top3_end}.")
    elif top3_end is not None:
        parts.append(f"You rank in the top 3 Maps pack in {top3_end} suburbs.")
    if pages_published:
        parts.append(f"{pages_published} content piece(s) published.")
    if gbp_posts:
        parts.append(f"{gbp_posts} GBP post(s) published.")
    if citations_ok:
        parts.append(f"{citations_ok} citation listing(s) verified consistent.")
    if in_progress:
        parts.append("This month is still in progress — figures update as you scan and publish.")
    return " ".join(parts)


async def _count_content_in_month(
    session: AsyncSession,
    client_id: UUID,
    month_start: datetime,
    month_end: datetime,
    *,
    content_type: str | None = None,
) -> int:
    q = """
        SELECT COUNT(*) AS n
        FROM rp_content_queue
        WHERE client_id = :cid
          AND status = 'published'
          AND published_at >= :start
          AND published_at <= :end
    """
    params: dict = {"cid": str(client_id), "start": month_start, "end": month_end}
    if content_type:
        q += " AND content_type = :ctype"
        params["ctype"] = content_type
    row = (await session.execute(text(q), params)).mappings().first()
    return int(row["n"] if row and row.get("n") is not None else 0)


async def _citations_verified_in_month(
    session: AsyncSession,
    client_id: UUID,
    month_start: datetime,
    month_end: datetime,
) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT COUNT(*) AS n
                FROM rp_citations
                WHERE client_id = :cid
                  AND drift_flag = false
                  AND last_checked >= :start
                  AND last_checked <= :end
                """
            ),
            {"cid": str(client_id), "start": month_start, "end": month_end},
        )
    ).mappings().first()
    return int(row["n"] if row and row.get("n") is not None else 0)


async def build_monthly_report(
    session: AsyncSession,
    client_id: UUID,
    month_start: datetime,
    keyword: str,
) -> dict:
    now = datetime.now(UTC)
    month_end = _month_end(month_start)
    in_progress = month_start.year == now.year and month_start.month == now.month
    as_of_end = now if in_progress else month_end + timedelta(seconds=1)

    start_rows = await _rank_rows_as_of(session, client_id, keyword, month_start)
    end_rows = await _rank_rows_as_of(session, client_id, keyword, as_of_end)

    vis_start = visibility_score_pct(start_rows) if any(r.get("rank_position") is not None for r in start_rows) else None
    vis_end = visibility_score_pct(end_rows) if any(r.get("rank_position") is not None for r in end_rows) else None
    top3_start, _, _, _ = count_rank_bands(start_rows) if start_rows else (None, None, None, None)
    top3_end, _, _, _ = count_rank_bands(end_rows) if end_rows else (None, None, None, None)

    if vis_start == 0.0 and not any(r.get("rank_position") is not None for r in start_rows):
        vis_start = None
    if vis_end == 0.0 and not any(r.get("rank_position") is not None for r in end_rows):
        vis_end = None

    pages = await _count_content_in_month(session, client_id, month_start, month_end)
    gbp_posts = await _count_content_in_month(
        session, client_id, month_start, month_end, content_type="gbp_post"
    )
    citations_ok = await _citations_verified_in_month(session, client_id, month_start, month_end)

    month_label = month_start.strftime("%B %Y")
    if in_progress:
        month_label += " (in progress)"

    narrative = _build_narrative(
        month_label=month_label,
        keyword=keyword or "your keyword",
        vis_start=vis_start,
        vis_end=vis_end,
        top3_start=top3_start,
        top3_end=top3_end,
        pages_published=pages,
        citations_ok=citations_ok,
        gbp_posts=gbp_posts,
        in_progress=in_progress,
    )

    return {
        "id": _report_id(client_id, month_start),
        "month": month_start.date().isoformat(),
        "visibility_score_start": vis_start,
        "visibility_score_end": vis_end,
        "top3_start": top3_start,
        "top3_end": top3_end,
        "pages_published": pages,
        "citations_fixed": citations_ok,
        "reviews_new": None,
        "gbp_posts": gbp_posts,
        "narrative_text": narrative,
        "pdf_url": _pdf_api_path(month_start.strftime("%Y-%m")),
    }


async def list_monthly_reports(session: AsyncSession, client_id: UUID) -> list[dict]:
    keyword = await _client_keyword(session, client_id)
    months = await _months_with_activity(session, client_id)
    if not months:
        return []

    reports: list[dict] = []
    for month_start in months:
        try:
            reports.append(await build_monthly_report(session, client_id, month_start, keyword))
        except Exception:
            logger.exception("Failed to build report for %s month %s", client_id, month_start)
    return reports
