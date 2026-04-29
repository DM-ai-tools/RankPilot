"""Google Business reviews via DataForSEO Business Data API (no GBP OAuth for read)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.schemas.reviews import (
    CompetitorVelocityItem,
    CompetitorVelocityResponse,
    ReviewItemRow,
    ReviewsSummaryResponse,
)
from app.services.dataforseo_service import DataForSEOClient, format_maps_location_name

logger = logging.getLogger(__name__)


def _metro_to_location_name(metro_label: str) -> str:
    raw = (metro_label or "").strip()
    if not raw:
        return format_maps_location_name("", "")
    if "," in raw:
        suburb, st = [x.strip() for x in raw.split(",", 1)]
        st_abbr = st[:10].strip()
        return format_maps_location_name(suburb, st_abbr)
    return format_maps_location_name(raw, "")


def _reviews_keyword(business_name: str, business_address: str, metro_label: str) -> str:
    name = (business_name or "").strip()
    addr = (business_address or "").strip()
    metro = (metro_label or "").strip()
    if addr:
        q = f"{name} {addr}"
    elif name and metro:
        q = f"{name} {metro}"
    else:
        q = name or metro or "business"
    return q[:700]


def _parse_review_ts(raw: object) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if len(s) < 19:
        return None
    core = s[:19]
    try:
        return datetime.strptime(core, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _rating_value(r: object) -> float | None:
    if not isinstance(r, dict):
        return None
    try:
        v = r.get("value")
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


class ReviewsService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def fetch_summary(self, client_id: UUID) -> ReviewsSummaryResponse:
        settings = get_settings()
        if not str(settings.dataforseo_login or "").strip() or not str(settings.dataforseo_password or "").strip():
            return ReviewsSummaryResponse(
                message="Add DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in backend/.env to load Google reviews.",
            )

        row = (
            await self._session.execute(
                text(
                    """
                    SELECT business_name, business_address, metro_label, gbp_location_id
                    FROM rp_clients
                    WHERE client_id = :cid
                    LIMIT 1
                    """
                ),
                {"cid": str(client_id)},
            )
        ).mappings().first()
        if not row:
            return ReviewsSummaryResponse(message="Client not found.")

        name = str(row["business_name"] or "")
        addr = str(row["business_address"] or "")
        metro = str(row["metro_label"] or "")
        gbp_id = str(row["gbp_location_id"] or "").strip()

        location_name = _metro_to_location_name(metro)
        if not location_name or location_name.count(",") < 1:
            return ReviewsSummaryResponse(
                message="Set a metro (e.g. Melbourne, VIC) on your profile so we can pass location_name to DataForSEO.",
            )

        place_id: str | None = None
        if gbp_id.startswith("ChIJ") or gbp_id.startswith("GhIJ"):
            place_id = gbp_id
        keyword = None if place_id else _reviews_keyword(name, addr, metro)

        client = DataForSEOClient(settings)
        try:
            block = await client.google_reviews_fetch_block(
                location_name=location_name,
                language_name="English",
                depth=30,
                sort_by="newest",
                keyword=keyword,
                place_id=place_id,
            )
        except Exception as exc:
            logger.exception("Google reviews fetch failed: %s", exc)
            return ReviewsSummaryResponse(
                message=f"DataForSEO error: {str(exc)}"[:500],
            )
        finally:
            await client.aclose()

        if not isinstance(block, dict):
            return ReviewsSummaryResponse(
                message="No review block returned — check business name/address or try connecting GBP for a place_id.",
            )

        items_raw = block.get("items")
        items_list = items_raw if isinstance(items_raw, list) else []

        agg_rating = block.get("rating")
        avg = _rating_value(agg_rating) if isinstance(agg_rating, dict) else None
        title = str(block.get("title") or "").strip() or None
        total_google = block.get("reviews_count")
        try:
            total_int = int(total_google) if total_google is not None else None
        except (TypeError, ValueError):
            total_int = None

        now = datetime.now(UTC)
        new_month = 0
        rows: list[ReviewItemRow] = []
        for it in items_list[:50]:
            if not isinstance(it, dict):
                continue
            t = str(it.get("type") or "")
            if t and t != "google_reviews_search":
                continue
            if not str(it.get("review_text") or "").strip():
                continue
            ts = _parse_review_ts(it.get("timestamp"))
            if ts and ts.year == now.year and ts.month == now.month:
                new_month += 1
            rv = it.get("rating")
            rows.append(
                ReviewItemRow(
                    rating=_rating_value(rv) if isinstance(rv, dict) else None,
                    review_text=str(it.get("review_text") or "")[:4000],
                    timestamp=str(it.get("timestamp") or "")[:40] or None,
                    profile_name=str(it.get("profile_name") or "")[:200] or None,
                    time_ago=str(it.get("time_ago") or "")[:80] or None,
                )
            )

        return ReviewsSummaryResponse(
            business_title=title,
            reviews_total_google=total_int,
            average_rating=avg,
            new_this_month=new_month,
            items_returned=len(rows),
            reviews=rows,
            fetched_at=now.isoformat(),
            message=None if rows or total_int is not None else "No reviews returned for this listing query — refine business name or address.",
        )

    async def fetch_competitor_velocity(self, client_id: UUID) -> CompetitorVelocityResponse:
        """
        Reads competitor names + review counts from rp_rank_history feature_snapshot rows
        (no extra DataForSEO API calls required — data was captured during the Maps scan).
        """
        # Client profile
        client_row = (
            await self._session.execute(
                text(
                    """
                    SELECT business_name, business_url
                    FROM rp_clients
                    WHERE client_id = :cid
                    LIMIT 1
                    """
                ),
                {"cid": str(client_id)},
            )
        ).mappings().first()
        if not client_row:
            return CompetitorVelocityResponse(note="Client not found.")

        client_domain_raw = str(client_row["business_url"] or "").strip()
        from urllib.parse import urlparse
        import re as _re
        def _norm_domain(url: str) -> str:
            if url and not url.startswith(("http://", "https://")):
                url = "https://" + url
            host = urlparse(url).netloc.lower()
            return _re.sub(r"^www\.", "", host)

        client_domain = _norm_domain(client_domain_raw)

        # Pull last 5 scan snapshots (most recent suburbs)
        history_rows = (
            await self._session.execute(
                text(
                    """
                    SELECT feature_snapshot
                    FROM rp_rank_history
                    WHERE client_id = :cid
                      AND feature_snapshot IS NOT NULL
                    ORDER BY checked_at DESC
                    LIMIT 10
                    """
                ),
                {"cid": str(client_id)},
            )
        ).mappings().all()

        if not history_rows:
            return CompetitorVelocityResponse(
                note="No scan data yet — run a Maps scan first to populate competitor data.",
            )

        # Aggregate: best (lowest rank) entry per domain/title
        import json as _json
        seen: dict[str, dict] = {}  # key = normalised domain or title
        for hr in history_rows:
            snap = hr["feature_snapshot"]
            if isinstance(snap, str):
                try:
                    snap = _json.loads(snap)
                except Exception:
                    continue
            if not isinstance(snap, dict):
                continue
            pack = snap.get("maps_pack")
            if not isinstance(pack, list):
                continue
            for item in pack:
                if not isinstance(item, dict):
                    continue
                dom = str(item.get("domain") or "").strip().lower()
                dom = _re.sub(r"^www\.", "", dom)
                title = str(item.get("title") or "").strip()
                key = dom if dom else title.lower()
                if not key:
                    continue
                rc_raw = item.get("reviews_count")
                try:
                    rc = int(rc_raw) if rc_raw is not None else None
                except (TypeError, ValueError):
                    rc = None
                rat_raw = item.get("rating")
                try:
                    rat = float(rat_raw) if rat_raw is not None else None
                except (TypeError, ValueError):
                    rat = None
                rank = item.get("rank")
                try:
                    rank_i = int(rank) if rank is not None else 999
                except (TypeError, ValueError):
                    rank_i = 999

                existing = seen.get(key)
                if existing is None or rank_i < existing.get("rank", 999):
                    seen[key] = {
                        "title": title,
                        "domain": dom or None,
                        "reviews_count": rc,
                        "rating": rat,
                        "rank": rank_i,
                    }

        if not seen:
            return CompetitorVelocityResponse(
                note="Scan snapshots found but no pack items extracted. Re-run a Maps scan.",
            )

        # Separate client vs competitors
        competitors: list[CompetitorVelocityItem] = []
        client_reviews_total: int | None = None

        for key, v in seen.items():
            dom = v.get("domain") or ""
            is_client = bool(client_domain and (dom == client_domain or client_domain in dom or dom in client_domain))
            rc = v.get("reviews_count")
            estimated = int(rc / 12) if rc is not None else None
            item = CompetitorVelocityItem(
                title=v["title"],
                domain=v.get("domain"),
                reviews_count=rc,
                rating=v.get("rating"),
                estimated_monthly=estimated,
                is_client=is_client,
            )
            if is_client:
                client_reviews_total = rc
            else:
                competitors.append(item)

        # Sort competitors by rank then by reviews_count desc
        competitors.sort(key=lambda c: (-(c.reviews_count or 0),))
        top_competitors = competitors[:5]

        return CompetitorVelocityResponse(
            client_title=str(client_row["business_name"] or ""),
            client_reviews_total=client_reviews_total,
            competitors=top_competitors,
            note="Review counts from Google Maps pack data captured during your last scan. Monthly velocity = total ÷ 12 (1-year estimate)." if top_competitors else "No competitor data in scan snapshots — reviews_count will populate after next Maps scan.",
        )
