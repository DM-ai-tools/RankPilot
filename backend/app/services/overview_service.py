"""L2: Dashboard overview — aggregates SEO tables (Maps ranks, content queue)."""

from datetime import UTC, datetime
from urllib.parse import quote_plus
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.lib.visibility_scoring import count_rank_bands, visibility_score_pct
from app.services.google_places_new_client import (
    display_name_text,
    place_details,
    places_search_text,
)
from app.schemas.dashboard import ScoreBlock
from app.schemas.dashboard_overview import (
    ActivityItem,
    BusinessProfileBlock,
    DashboardOverviewResponse,
    DashboardScoresPart,
    GaugeBlock,
    RankWinRow,
    RecommendationRow,
    StatBlock,
)


def _primary_state_from_metro(metro: str) -> str | None:
    """Infer AU state abbreviation from metro_label text (e.g. 'Sydney, NSW' → NSW)."""
    u = (metro or "").upper()
    for abbr in ("NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"):
        if abbr in u:
            return abbr
    return None


def _iso_week_label(now: datetime) -> str:
    now = now.astimezone(UTC)
    iso = now.isocalendar()
    return f"ISO week {iso.week} · {now.year}"


def _maps_search_url(name: str, address: str, metro: str) -> str:
    q = " ".join(x for x in [name.strip(), address.strip(), metro.strip()] if x)
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(q)}" if q else ""


def _norm_host(url: str) -> str:
    raw = (url or "").strip().lower()
    if not raw:
        return ""
    raw = raw.replace("https://", "").replace("http://", "").replace("www.", "")
    return raw.split("/")[0].strip()


def _host_matches(expected: str, actual: str) -> bool:
    e = (expected or "").strip().lower()
    a = (actual or "").strip().lower()
    if not e or not a:
        return False
    if e == a:
        return True
    return e.endswith("." + a) or a.endswith("." + e)


async def _google_places_business_details(
    business_name: str,
    business_url: str,
    metro: str,
    api_key: str,
) -> dict | None:
    if not api_key.strip():
        return None
    expected_host = _norm_host(business_url)
    queries: list[str] = []
    if business_name.strip():
        queries.append(" ".join(x for x in [business_name.strip(), metro.strip()] if x))
    if expected_host:
        queries.append(" ".join(x for x in [expected_host, metro.strip()] if x))
        queries.append(expected_host)
    if business_name.strip():
        queries.append(business_name.strip())

    async with httpx.AsyncClient(timeout=20) as client:
        rows: list[dict] = []
        seen_place_ids: set[str] = set()
        for query in queries:
            if not query:
                continue
            try:
                found = await places_search_text(client, api_key, query, page_size=10)
            except httpx.HTTPStatusError:
                continue
            for row in found[:5]:
                pid = str(row.get("id") or "").strip()
                if not pid or pid in seen_place_ids:
                    continue
                seen_place_ids.add(pid)
                rows.append(row)
        if not rows:
            return None

        # Prefer a Place whose website matches our saved business_url (strict GBP match).
        # If none match — common when GMB omits website, uses a redirect, or uses a different domain —
        # still return the first Text Search hit with full details. That is the same entity users see
        # when opening the Maps search link built from business name + metro.
        matched: dict | None = None
        fallback: dict | None = None
        for r in rows[:10]:
            pid = str(r.get("id") or "").strip()
            if not pid:
                continue
            try:
                detail = await place_details(client, api_key, pid)
            except httpx.HTTPStatusError:
                continue
            if not detail:
                continue
            website = str(detail.get("websiteUri") or "").strip().lower()
            host = _norm_host(website)
            result = {
                "name": display_name_text(detail) or display_name_text(r),
                "address": str(detail.get("formattedAddress") or r.get("formattedAddress") or "").strip(),
                "phone": str(
                    detail.get("internationalPhoneNumber")
                    or detail.get("nationalPhoneNumber")
                    or ""
                ).strip(),
                "maps_url": str(detail.get("googleMapsUri") or "").strip(),
            }
            if fallback is None:
                fallback = result
            if expected_host and host and _host_matches(expected_host, host):
                matched = result
                break
        if matched is not None:
            return matched
        return fallback


class OverviewService:
    async def build(self, session: AsyncSession, client_id: UUID) -> DashboardOverviewResponse:
        settings = get_settings()
        client_row = (
            await session.execute(
                text(
                    """
                    SELECT client_id, primary_keyword, metro_label, business_url, business_name, business_address, business_phone
                    FROM rp_clients
                    WHERE client_id = :cid
                    """
                ),
                {"cid": str(client_id)},
            )
        ).mappings().first()
        if not client_row:
            return self._empty_overview()

        keyword = str(client_row["primary_keyword"] or "").strip()
        metro = str(client_row["metro_label"] or "")
        business_name = str(client_row["business_name"] or "").strip()
        business_url = str(client_row["business_url"] or "").strip()
        business_address = str(client_row["business_address"] or "").strip()
        business_phone = str(client_row["business_phone"] or "").strip()
        profile_source = "profile"

        if settings.google_places_api_key.strip():
            try:
                google_data = await _google_places_business_details(
                    business_name=business_name,
                    business_url=business_url,
                    metro=metro,
                    api_key=settings.google_places_api_key.strip(),
                )
                if google_data:
                    business_name = str(google_data.get("name") or business_name).strip() or business_name
                    business_address = str(google_data.get("address") or business_address).strip() or business_address
                    business_phone = str(google_data.get("phone") or business_phone).strip() or business_phone
                    profile_source = "google_places"
                    await session.execute(
                        text(
                            """
                            UPDATE rp_clients
                            SET business_address = :addr,
                                business_phone = :phone,
                                updated_at = now()
                            WHERE client_id = :cid
                            """
                        ),
                        {"cid": str(client_id), "addr": business_address, "phone": business_phone},
                    )
                    await session.commit()
            except Exception:
                # Keep dashboard responsive and fallback to saved profile values.
                pass

        rank_rows = (
            await session.execute(
                text(
                    """
                    SELECT DISTINCT ON (s.id)
                      s.id AS suburb_id,
                      s.suburb,
                      s.state,
                      s.postcode,
                      s.lat,
                      s.lng,
                      s.population,
                      r.rank_position,
                      r.feature_snapshot
                    FROM rp_suburb_grid s
                    LEFT JOIN rp_rank_history r
                      ON r.suburb_id = s.id
                     AND LOWER(TRIM(r.keyword)) = LOWER(TRIM(:kw))
                     AND r.client_id = :cid
                    WHERE s.client_id = :cid
                    ORDER BY s.id, r.checked_at DESC NULLS LAST
                    """
                ),
                {"kw": keyword, "cid": str(client_id)},
            )
        ).mappings().all()

        total = len(rank_rows)
        top3, page1, pack_11_20, not_ranking = count_rank_bands(rank_rows)
        ranked = top3 + page1 + pack_11_20

        # Google Ads volumes from DataForSEO (one number per AU state, copied onto each suburb row).
        # Do NOT sum all states — that inflates vs Keyword Planner (e.g. 10k from NSW+VIC+QLD+…).
        # Use the metro's primary state when detectable; else the highest single-state value.
        state_monthly: dict[str, int] = {}
        for r in rank_rows:
            st = str(r.get("state") or "").upper()
            snap = r.get("feature_snapshot")
            if not st or not isinstance(snap, dict):
                continue
            raw = snap.get("monthly_search_volume")
            if raw is None:
                continue
            try:
                state_monthly[st] = max(state_monthly.get(st, 0), int(raw))
            except (TypeError, ValueError):
                continue

        monthly_note: str | None = None
        if state_monthly:
            primary_st = _primary_state_from_metro(metro)
            if primary_st and primary_st in state_monthly:
                monthly = int(state_monthly[primary_st])
                monthly_note = f"Google Ads vol. · {primary_st} (matches DataForSEO state scope)"
            else:
                monthly = int(max(state_monthly.values()))
                monthly_note = "Google Ads vol. · highest tracked state (metro had no clear state)"
        else:
            # No completed scan yet (or volume API failed): heuristic from suburb populations only.
            pop_sum = sum(int(r["population"] or 0) for r in rank_rows)
            monthly = int(pop_sum * 14 / 1000) if pop_sum else 0
            monthly_note = "Estimate only — run a Maps scan to pull DataForSEO volumes"

        total_safe = max(total, 1)
        top3_pct = min(100, int(round(100 * top3 / total_safe)))
        page1_pct = min(100, int(round(100 * page1 / total_safe)))
        p11_pct = min(100, int(round(100 * pack_11_20 / total_safe)))
        nr_pct = min(100, int(round(100 * not_ranking / total_safe)))

        seo = visibility_score_pct(rank_rows)

        content_rows = (
            await session.execute(
                text(
                    """
                    SELECT content_type, payload, status, generated_at, created_at
                    FROM rp_content_queue
                    WHERE client_id = :cid
                    ORDER BY COALESCE(generated_at, created_at) DESC
                    LIMIT 8
                    """
                ),
                {"cid": str(client_id)},
            )
        ).mappings().all()

        activity: list[ActivityItem] = []
        now = datetime.now(UTC)
        for cr in content_rows:
            title = ""
            if cr["payload"] and isinstance(cr["payload"], dict):
                title = str(cr["payload"].get("title") or "")
            ts = cr["generated_at"] or cr["created_at"]
            if ts is None:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            activity.append(
                ActivityItem(
                    icon="📄" if cr["content_type"] != "gbp_description" else "🏢",
                    heading=f"{cr['content_type'].replace('_', ' ').title()}",
                    detail=title or "Queued content",
                    occurred_at=ts,
                )
            )

        recs = self._default_recommendations(top3, page1 + pack_11_20, not_ranking)

        return DashboardOverviewResponse(
            scores=DashboardScoresPart(
                seo_visibility=ScoreBlock(value=float(seo), delta_4w=None),
            ),
            week_label=_iso_week_label(now),
            keyword=keyword,
            metro_label=metro,
            business_profile=BusinessProfileBlock(
                name=business_name or "Not found",
                address=business_address or "Not found",
                phone=business_phone or "Not found",
                maps_url=_maps_search_url(business_name, business_address, metro),
                source=profile_source,
            ),
            stats=StatBlock(
                visibility_score=float(seo),
                visibility_delta=None,
                suburbs_ranked=ranked,
                suburbs_total=total,
                monthly_searches=monthly,
                monthly_volume_note=monthly_note,
                missed_suburbs=not_ranking,
                missed_note="High-population suburbs not in Maps pack (top 20)" if not_ranking else None,
            ),
            gauge=GaugeBlock(
                top3_count=top3,
                page1_count=page1,
                pack_11_20_count=pack_11_20,
                not_ranking_count=not_ranking,
                top3_pct=top3_pct,
                page1_pct=page1_pct,
                pack_11_20_pct=p11_pct,
                not_ranking_pct=nr_pct,
            ),
            activity=activity,
            rank_wins=[],
            recommendations=recs,
        )

    def _default_recommendations(self, _top3: int, pack_visible: int, not_ranking: int) -> list[RecommendationRow]:
        recs: list[RecommendationRow] = []
        if not_ranking > 0:
            recs.append(
                RecommendationRow(
                    icon="📄",
                    title="Publish suburb landing pages",
                    subtitle=f"{not_ranking} suburbs are outside the top-20 Maps pack for your keyword.",
                    priority="high",
                )
            )
        if pack_visible < 15:
            recs.append(
                RecommendationRow(
                    icon="🏢",
                    title="Expand GBP service areas",
                    subtitle="Align Google Business Profile service list with suburb grid.",
                    priority="med",
                )
            )
        recs.append(
            RecommendationRow(
                icon="🔗",
                title="Build AU citations",
                subtitle="Close gaps on high-DA directories (TrueLocal, Yelp, Yellow).",
                priority="low",
            )
        )
        return recs[:3]

    def _empty_overview(self) -> DashboardOverviewResponse:
        z = ScoreBlock(value=0.0, delta_4w=None)
        return DashboardOverviewResponse(
            scores=DashboardScoresPart(seo_visibility=z),
            week_label=_iso_week_label(datetime.now(UTC)),
            keyword="",
            metro_label="",
            business_profile=None,
            stats=StatBlock(
                visibility_score=0.0,
                suburbs_ranked=0,
                suburbs_total=0,
                monthly_searches=0,
                monthly_volume_note=None,
                missed_suburbs=0,
            ),
            gauge=GaugeBlock(
                top3_count=0,
                page1_count=0,
                pack_11_20_count=0,
                not_ranking_count=0,
                top3_pct=0,
                page1_pct=0,
                pack_11_20_pct=0,
                not_ranking_pct=0,
            ),
            activity=[],
            rank_wins=[],
            recommendations=[],
        )
