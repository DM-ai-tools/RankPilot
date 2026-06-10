"""Live suburb keyword volumes and suggestions — Ahrefs only."""

from __future__ import annotations

import logging
import re
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_ahrefs_api_key
from app.lib.primary_keywords import normalize_primary_keywords, parse_primary_keywords
from app.schemas.keywords import (
    RelatedKeywordIdea,
    SuburbKeywordPhrase,
    SuburbKeywordResearchResponse,
)
from app.services.ahrefs_cache_service import build_cache_key, cache_timestamps_iso, get_ahrefs_cache, set_ahrefs_cache
from app.services.ahrefs_service import AhrefsClient
from app.services.keyword_lookup_service import _country_for_metro
from app.services.overview_service import _primary_state_from_metro

logger = logging.getLogger(__name__)


def _metro_city_name(metro_label: str) -> str:
    """e.g. Melbourne, VIC → Melbourne"""
    label = (metro_label or "").strip()
    if not label:
        return ""
    return label.split(",")[0].strip()


def _city_phrases(primary: str, city: str, state: str = "") -> list[str]:
    primary = re.sub(r"\s+", " ", (primary or "").strip())
    city = re.sub(r"\s+", " ", (city or "").strip())
    st = (state or "").strip().upper()
    if not primary or not city:
        return []
    out: list[str] = []
    seen: set[str] = set()
    candidates = [
        f"{primary} {city}",
        f"{city} {primary}",
        f"{primary} near {city}",
        f"{primary} services {city}",
    ]
    if st:
        candidates.extend([f"{primary} {city} {st}", f"{primary} {city} australia"])
    for phrase in candidates:
        key = phrase.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(phrase)
    return out


def _suburb_phrases(primary: str, suburb: str) -> list[str]:
    primary = re.sub(r"\s+", " ", (primary or "").strip())
    suburb = re.sub(r"\s+", " ", (suburb or "").strip())
    if not primary or not suburb:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for phrase in (
        f"{primary} {suburb}",
        f"{suburb} {primary}",
        f"{primary} near {suburb}",
    ):
        key = phrase.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(phrase)
    return out


def _suburb_in_keyword(keyword: str, suburb: str) -> bool:
    return suburb.lower() in (keyword or "").lower()


def _phrase_from_ahrefs_row(
    phrase: str,
    suburb: str,
    st: str,
    row: dict,
) -> SuburbKeywordPhrase:
    vol = row.get("volume")
    return SuburbKeywordPhrase(
        keyword=phrase,
        suburb=suburb,
        state=st or None,
        avg_monthly_searches=int(vol) if isinstance(vol, int) else 0,
        competition=row.get("competition"),
        difficulty=row.get("difficulty"),
        opportunity_score=int(row.get("opportunity_score") or 0),
        traffic_potential=row.get("traffic_potential"),
    )


def _idea_from_ahrefs_row(kw: str, suburb: str | None, row: dict) -> RelatedKeywordIdea:
    vol = row.get("volume")
    return RelatedKeywordIdea(
        keyword=kw,
        suburb=suburb,
        avg_monthly_searches=int(vol) if isinstance(vol, int) else 0,
        competition=row.get("competition"),
        difficulty=row.get("difficulty"),
        opportunity_score=int(row.get("opportunity_score") or 0),
        traffic_potential=row.get("traffic_potential"),
    )


_JUNK_KEYWORD_RE = re.compile(r"\.(com|au|net|org|io)\b|https?://|www\.|\bby\s+\w+\.com", re.I)


def _is_junk_keyword(kw: str) -> bool:
    text = (kw or "").strip()
    if len(text) < 4 or len(text) > 90:
        return True
    if _JUNK_KEYWORD_RE.search(text):
        return True
    return text.count(" ") > 12


def _primary_tokens(primary: str | list[str]) -> set[str]:
    if isinstance(primary, str):
        sources = parse_primary_keywords(primary) or [primary.strip()]
    else:
        sources = primary
    tokens: set[str] = set()
    for src in sources:
        if not src.strip():
            continue
        tokens.update(
            w.lower()
            for w in re.sub(r"\s+", " ", src.strip()).split()
            if len(w) > 2
        )
    return tokens


def _is_relevant_local_keyword(kw: str, primary: str | list[str], location_names: list[str]) -> bool:
    """Drop unrelated Ahrefs noise — keep local + service-intent phrases only."""
    if _is_junk_keyword(kw):
        return False
    low = kw.lower()
    loc_hit = any(name.lower() in low for name in location_names if name.strip())
    primary_hit = any(tok in low for tok in _primary_tokens(primary))
    return loc_hit and primary_hit


def _phrase_to_idea(phrase: SuburbKeywordPhrase) -> RelatedKeywordIdea:
    return RelatedKeywordIdea(
        keyword=phrase.keyword,
        suburb=phrase.suburb,
        avg_monthly_searches=phrase.avg_monthly_searches,
        competition=phrase.competition,
        difficulty=phrase.difficulty,
        opportunity_score=phrase.opportunity_score,
        traffic_potential=phrase.traffic_potential,
    )


def _build_top_keywords(
    phrases: list[SuburbKeywordPhrase],
    related: list[RelatedKeywordIdea],
    *,
    primary: str | list[str],
    location_names: list[str],
    limit: int = 30,
) -> list[RelatedKeywordIdea]:
    """Merge live Ahrefs data into one ranked list for GBP content."""
    ranked: list[RelatedKeywordIdea] = []
    seen: set[str] = set()

    for phrase in sorted(
        phrases,
        key=lambda x: (int(x.opportunity_score or 0), int(x.avg_monthly_searches or 0)),
        reverse=True,
    ):
        key = phrase.keyword.lower()
        if key in seen:
            continue
        seen.add(key)
        ranked.append(_phrase_to_idea(phrase))

    for idea in sorted(
        related,
        key=lambda x: (int(x.opportunity_score or 0), int(x.avg_monthly_searches or 0)),
        reverse=True,
    ):
        if not _is_relevant_local_keyword(idea.keyword, primary, location_names):
            continue
        key = idea.keyword.lower()
        if key in seen:
            continue
        seen.add(key)
        ranked.append(idea)

    ranked.sort(
        key=lambda x: (int(x.opportunity_score or 0), int(x.avg_monthly_searches or 0)),
        reverse=True,
    )
    return ranked[: max(5, min(int(limit), 50))]


async def _collect_ahrefs_ideas(
    client: AhrefsClient,
    *,
    seeds: list[str],
    suburbs: list[str],
    country: str,
    idea_limit: int,
) -> list[RelatedKeywordIdea]:
    """Live Ahrefs discovery: matching + related + search suggestions."""
    related: list[RelatedKeywordIdea] = []
    seen: set[str] = set()

    async def add_rows(rows: list[dict]) -> None:
        for row in rows:
            kw = str(row.get("keyword") or "").strip()
            if not kw or kw.lower() in seen:
                continue
            seen.add(kw.lower())
            area_match = next((s for s in suburbs if s.lower() in kw.lower()), None)
            related.append(_idea_from_ahrefs_row(kw, area_match, row))

    per_seed = max(15, min(int(idea_limit), 40))
    for seed in seeds[:8]:
        if not seed.strip():
            continue
        try:
            await add_rows(await client.matching_terms(seed, country=country, limit=per_seed))
        except Exception as exc:
            logger.warning("Ahrefs matching_terms skipped for %r: %s", seed, exc)
        try:
            await add_rows(await client.related_terms(seed, country=country, limit=per_seed))
        except Exception as exc:
            logger.warning("Ahrefs related_terms skipped for %r: %s", seed, exc)
        try:
            await add_rows(await client.search_suggestions(seed, country=country, limit=20))
        except Exception as exc:
            logger.warning("Ahrefs search_suggestions skipped for %r: %s", seed, exc)

    related.sort(
        key=lambda x: (int(x.opportunity_score or 0), int(x.avg_monthly_searches or 0)),
        reverse=True,
    )
    return related


async def _fetch_via_ahrefs(
    *,
    primary: str,
    primaries: list[str],
    metro: str,
    geo_label: str,
    suburbs: list[str],
    phrase_specs: list[tuple[str, str, str]],
    idea_limit: int,
    location_scope: str = "suburb",
) -> SuburbKeywordResearchResponse:
    country = _country_for_metro(metro)
    client = AhrefsClient()
    try:
        unique_phrases = list(dict.fromkeys(p for p, _, _ in phrase_specs))
        overview_rows = await client.keywords_overview(unique_phrases, country=country)
        vol_by_kw = {str(r["keyword"]).lower(): r for r in overview_rows}

        suburb_phrase_out: list[SuburbKeywordPhrase] = []
        for phrase, suburb, st in phrase_specs:
            row = vol_by_kw.get(phrase.lower(), {})
            suburb_phrase_out.append(_phrase_from_ahrefs_row(phrase, suburb, st, row))
        suburb_phrase_out.sort(key=lambda x: x.opportunity_score, reverse=True)

        city_name = _metro_city_name(metro)
        location_names = [s for s in suburbs if s]
        if city_name and city_name.lower() not in {s.lower() for s in location_names}:
            location_names.insert(0, city_name)

        seeds: list[str] = []
        for pk in primaries:
            if suburbs:
                seeds.append(f"{pk} {suburbs[0]}")
            if city_name:
                seeds.append(f"{pk} {city_name}")
            seeds.append(pk)
        seeds = list(dict.fromkeys(s for s in seeds if s.strip()))

        related = await _collect_ahrefs_ideas(
            client,
            seeds=seeds,
            suburbs=suburbs,
            country=country,
            idea_limit=idea_limit,
        )
        related = [
            r for r in related
            if _is_relevant_local_keyword(r.keyword, primaries, location_names)
        ]
        related.sort(
            key=lambda x: (int(x.opportunity_score or 0), int(x.avg_monthly_searches or 0)),
            reverse=True,
        )
        related = related[: max(5, min(int(idea_limit), 50))]

        top_keywords = _build_top_keywords(
            suburb_phrase_out,
            related,
            primary=primaries,
            location_names=location_names,
            limit=30,
        )
    finally:
        await client.aclose()

    return SuburbKeywordResearchResponse(
        primary_keyword=primary,
        metro_label=metro,
        geo_label=geo_label or country.upper(),
        location_scope=location_scope,
        suburbs=suburbs,
        suburb_phrases=suburb_phrase_out,
        related_ideas=related,
        top_keywords=top_keywords,
        source="ahrefs",
        message=None,
    )


async def fetch_suburb_keyword_research(
    session: AsyncSession,
    client_id: UUID,
    *,
    suburb_limit: int = 8,
    idea_limit: int = 30,
    force_refresh: bool = False,
) -> SuburbKeywordResearchResponse:
    if not get_ahrefs_api_key():
        return SuburbKeywordResearchResponse(
            message="Set AHREFS_API_KEY in backend/.env and restart the API. Keyword data uses Ahrefs only.",
            source="none",
        )

    profile = (
        await session.execute(
            text(
                """
                SELECT primary_keyword, metro_label,
                       COALESCE(location_scope, 'suburb') AS location_scope,
                       COALESCE(primary_suburb, '') AS primary_suburb
                FROM rp_clients
                WHERE client_id = :cid
                LIMIT 1
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    primary = normalize_primary_keywords(str((profile or {}).get("primary_keyword") or "").strip())
    primaries = parse_primary_keywords(primary)
    metro = str((profile or {}).get("metro_label") or "").strip()
    scope = str((profile or {}).get("location_scope") or "suburb").strip().lower()
    anchor_suburb = str((profile or {}).get("primary_suburb") or "").strip()
    if not primaries:
        raise HTTPException(status_code=400, detail="Set a primary keyword in onboarding first.")

    state_abbr = _primary_state_from_metro(metro) or "VIC"
    geo_label = f"{state_abbr}, Australia"
    city_name = _metro_city_name(metro)

    phrase_specs: list[tuple[str, str, str]] = []
    suburbs: list[str] = []

    if scope == "city":
        if not city_name:
            return SuburbKeywordResearchResponse(
                primary_keyword=primary,
                metro_label=metro,
                location_scope="city",
                message="Set a city/metro in Business Setup first.",
                source="none",
            )
        suburbs = [city_name]
        for pk in primaries:
            for phrase in _city_phrases(pk, city_name, state_abbr):
                phrase_specs.append((phrase, city_name, state_abbr))
    else:
        lim = max(1, min(int(suburb_limit), 12))
        suburb_rows = (
            await session.execute(
                text(
                    """
                    SELECT suburb, state
                    FROM rp_suburb_grid
                    WHERE client_id = :cid
                    ORDER BY rank_priority ASC
                    LIMIT :lim
                    """
                ),
                {"cid": str(client_id), "lim": lim},
            )
        ).mappings().all()
        if not suburb_rows:
            return SuburbKeywordResearchResponse(
                primary_keyword=primary,
                metro_label=metro,
                location_scope="suburb",
                message="No suburbs in your grid — complete onboarding or widen your service radius.",
                source="none",
            )

        suburbs = [str(r["suburb"]) for r in suburb_rows]
        if anchor_suburb:
            suburbs = [anchor_suburb] + [s for s in suburbs if s.lower() != anchor_suburb.lower()]
            suburbs = suburbs[:lim]

        state_counts: dict[str, int] = {}
        for r in suburb_rows:
            st = str(r.get("state") or "").upper()
            if st:
                state_counts[st] = state_counts.get(st, 0) + 1
        if state_counts:
            state_abbr = max(state_counts, key=state_counts.get)

        for suburb in suburbs:
            for pk in primaries:
                for phrase in _suburb_phrases(pk, suburb):
                    phrase_specs.append((phrase, suburb, state_abbr))

    country = _country_for_metro(metro)
    cache_key = build_cache_key(
        "suburb_research",
        country,
        str(client_id),
        primary,
        scope,
        anchor_suburb or city_name,
        str(suburb_limit),
        str(idea_limit),
    )
    if not force_refresh:
        cached, fetched_at, expires_at = await get_ahrefs_cache(session, cache_key)
        if cached:
            cached_at_s, expires_s = cache_timestamps_iso(fetched_at, expires_at)
            out = SuburbKeywordResearchResponse.model_validate(cached)
            out.from_cache = True
            out.cached_at = cached_at_s
            out.cache_expires_at = expires_s
            return out

    try:
        result = await _fetch_via_ahrefs(
            primary=primary,
            primaries=primaries,
            metro=metro,
            geo_label=geo_label,
            suburbs=suburbs,
            phrase_specs=phrase_specs,
            idea_limit=idea_limit if scope != "city" else max(idea_limit, 40),
            location_scope=scope,
        )
        await set_ahrefs_cache(
            session,
            cache_key,
            result.model_dump(mode="json", exclude={"from_cache", "cached_at", "cache_expires_at"}),
            client_id=client_id,
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Ahrefs suburb keyword research failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ahrefs keyword research failed: {exc}",
        ) from exc
