"""Ahrefs Keyword Explorer overview — metrics + idea columns."""

from __future__ import annotations

import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_ahrefs_api_key
from app.schemas.keywords import (
    GlobalVolumeCountry,
    KeywordIdeaItem,
    KeywordOverviewMetrics,
    KeywordOverviewResponse,
)
from app.services.ahrefs_cache_service import (
    build_cache_key,
    cache_timestamps_iso,
    get_ahrefs_cache,
    set_ahrefs_cache,
)
from app.services.ahrefs_service import AhrefsClient, difficulty_label, format_volume_display, kd_short_label
from app.services.keyword_lookup_service import _country_for_metro

_COUNTRY_LABELS: dict[str, str] = {
    "au": "Australia",
    "nz": "New Zealand",
    "us": "United States",
    "gb": "United Kingdom",
    "ca": "Canada",
}


def _idea_from_row(row: dict) -> KeywordIdeaItem:
    vol = row.get("volume")
    gv = row.get("global_volume")
    return KeywordIdeaItem(
        keyword=str(row.get("keyword") or ""),
        volume=vol if isinstance(vol, int) else None,
        volume_display=str(row.get("volume_display") or format_volume_display(vol, global_volume=gv)),
        difficulty=row.get("difficulty"),
        competition=row.get("competition"),
    )


def _metrics_from_row(keyword: str, row: dict, *, country: str) -> KeywordOverviewMetrics:
    kd = row.get("difficulty")
    vol = row.get("volume")
    gv = row.get("global_volume")
    tp = row.get("traffic_potential")
    kd_int = int(kd) if kd is not None else None
    history = row.get("volume_monthly_history") or []
    chart: list[int] = []
    if isinstance(history, list):
        for point in history:
            if isinstance(point, dict):
                try:
                    chart.append(int(point.get("volume") or 0))
                except (TypeError, ValueError):
                    chart.append(0)
            elif isinstance(point, (int, float)):
                chart.append(int(point))

    global_countries: list[GlobalVolumeCountry] = []
    if gv is not None and int(gv) > 0:
        global_countries.append(
            GlobalVolumeCountry(
                country_code=country,
                country_name=_COUNTRY_LABELS.get(country, country.upper()),
                volume=int(gv),
                share_pct=100,
            )
        )

    return KeywordOverviewMetrics(
        keyword=keyword,
        volume=vol if isinstance(vol, int) else None,
        volume_display=str(row.get("volume_display") or format_volume_display(vol, global_volume=gv)),
        difficulty=kd_int,
        difficulty_label=difficulty_label(kd_int),
        difficulty_short=kd_short_label(kd_int),
        kd_description=_kd_description(kd_int),
        traffic_potential=int(tp) if tp is not None else None,
        global_volume=int(gv) if gv is not None else None,
        volume_chart=chart,
        global_by_country=global_countries,
    )


# Filler words ignored when checking whether a related keyword is on-topic.
_RELEVANCE_STOPWORDS = {
    "a", "an", "and", "at", "best", "by", "for", "from", "how", "in", "is",
    "me", "my", "near", "of", "on", "or", "the", "to", "top", "what", "where",
    "which", "who", "why", "with", "your",
}


def _seed_terms(keyword: str) -> set[str]:
    return {
        t
        for t in re.split(r"[^a-z0-9]+", keyword.lower())
        if len(t) >= 3 and t not in _RELEVANCE_STOPWORDS
    }


def _is_relevant(candidate: str, seed_terms: set[str]) -> bool:
    """True if the candidate keyword shares at least one meaningful term (stem match)."""
    if not seed_terms:
        return True
    tokens = {t for t in re.split(r"[^a-z0-9]+", candidate.lower()) if len(t) >= 3}
    for tok in tokens:
        for seed in seed_terms:
            # Prefix stem match: "agency"~"agencies", "consultant"~"consultants".
            if tok.startswith(seed[:4]) and seed.startswith(tok[:4]):
                return True
    return False


def _filter_relevant(rows: list[dict], seed_terms: set[str]) -> list[dict]:
    """Drop Ahrefs filler (chatgpt, youtube, …) returned for low-data seed keywords."""
    return [r for r in rows if _is_relevant(str(r.get("keyword") or ""), seed_terms)]


def _kd_description(kd: int | None) -> str:
    if kd is None:
        return "Difficulty data not available for this keyword."
    if kd <= 10:
        return "Very few referring domains needed to rank in the top 10."
    if kd <= 30:
        return "Moderate competition — achievable with solid content and some links."
    if kd <= 50:
        return "Competitive keyword — expect to need authority and backlinks."
    return "Highly competitive — strong domain authority required."


async def fetch_keyword_overview(
    session: AsyncSession,
    client_id: UUID,
    *,
    keyword: str,
    country: str | None = None,
    force_refresh: bool = False,
) -> KeywordOverviewResponse:
    keyword = " ".join((keyword or "").split()).strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="Enter a keyword to analyze.")

    if not get_ahrefs_api_key():
        return KeywordOverviewResponse(
            keyword=keyword,
            message="Set AHREFS_API_KEY in backend/.env and restart the API.",
            source="none",
        )

    profile = (
        await session.execute(
            text("SELECT metro_label FROM rp_clients WHERE client_id = :cid LIMIT 1"),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    metro = str((profile or {}).get("metro_label") or "")
    cc = (country or _country_for_metro(metro) or "au").strip().lower()[:2]
    # v2: bypasses pre-relevance-filter cached responses
    cache_key = build_cache_key("overview-v2", cc, keyword)

    if not force_refresh:
        cached, fetched_at, expires_at = await get_ahrefs_cache(session, cache_key)
        if cached:
            cached_at_s, expires_s = cache_timestamps_iso(fetched_at, expires_at)
            out = KeywordOverviewResponse.model_validate(cached)
            out.from_cache = True
            out.cached_at = cached_at_s
            out.cache_expires_at = expires_s
            return out

    client = AhrefsClient()
    try:
        overview_row = await client.keyword_overview_one(keyword, country=cc)
        terms_match = await client.matching_terms(keyword, country=cc, limit=25, terms="all")
        questions = await client.matching_terms(keyword, country=cc, limit=15, terms="questions")
        also_rank_for = await client.related_terms(
            keyword, country=cc, limit=15, terms="also_rank_for"
        )
        also_talk_about = await client.related_terms(
            keyword, country=cc, limit=15, terms="also_talk_about"
        )
        seed_terms = _seed_terms(keyword)
        also_rank_for = _filter_relevant(also_rank_for, seed_terms)
        also_talk_about = _filter_relevant(also_talk_about, seed_terms)
        if not also_rank_for:
            also_rank_for = _filter_relevant(
                await client.search_suggestions(keyword, country=cc, limit=12), seed_terms
            )
    finally:
        await client.aclose()

    metrics = _metrics_from_row(keyword, overview_row, country=cc)

    def _dedupe_ideas(rows: list[dict], *, exclude: str) -> list[KeywordIdeaItem]:
        seen: set[str] = {exclude.lower()}
        out: list[KeywordIdeaItem] = []
        for row in rows:
            kw = str(row.get("keyword") or "").strip()
            if not kw or kw.lower() in seen:
                continue
            seen.add(kw.lower())
            out.append(_idea_from_row(row))
        return out

    response = KeywordOverviewResponse(
        keyword=keyword,
        country=cc,
        country_label=_COUNTRY_LABELS.get(cc, cc.upper()),
        metrics=metrics,
        terms_match=_dedupe_ideas(terms_match, exclude=keyword),
        questions=_dedupe_ideas(questions, exclude=keyword),
        also_rank_for=_dedupe_ideas(also_rank_for, exclude=keyword),
        also_talk_about=_dedupe_ideas(also_talk_about, exclude=keyword),
        source="ahrefs",
        message=None,
        from_cache=False,
    )
    await set_ahrefs_cache(
        session,
        cache_key,
        response.model_dump(mode="json", exclude={"from_cache", "cached_at", "cache_expires_at"}),
        client_id=client_id,
    )
    return response
