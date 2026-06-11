"""Competitor GBP post analysis — what your Maps competitors post and when.

Pulls each competitor's Google Business Profile posts ("updates") via
DataForSEO Business Data, then analyzes posting cadence, keyword usage,
and the terms they use on a regular basis.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import Counter
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.schemas.keywords import (
    CompetitorGbpPost,
    CompetitorGbpPostsItem,
    CompetitorGbpPostsResponse,
)
from app.services.ahrefs_cache_service import (
    build_cache_key,
    get_ahrefs_cache,
    set_ahrefs_cache,
)
from app.services.dataforseo_service import DataForSEOClient, format_maps_location_name

logger = logging.getLogger(__name__)

_MAX_COMPETITORS = 3
_POST_DEPTH = 20

_TERM_STOPWORDS = {
    "a", "about", "all", "an", "and", "are", "as", "at", "be", "been", "best",
    "but", "by", "call", "can", "contact", "day", "do", "for", "from", "get",
    "has", "have", "here", "how", "if", "in", "is", "it", "its", "just",
    "more", "most", "need", "new", "no", "not", "now", "of", "on", "one",
    "or", "our", "out", "so", "team", "than", "that", "the", "their", "them",
    "there", "they", "this", "to", "today", "top", "us", "we", "what", "when",
    "where", "which", "who", "why", "will", "with", "you", "your",
}


def _metro_to_location_name(metro_label: str) -> str:
    raw = (metro_label or "").strip()
    if not raw:
        return format_maps_location_name("", "")
    if "," in raw:
        suburb, st = [x.strip() for x in raw.split(",", 1)]
        return format_maps_location_name(suburb, st[:10].strip())
    return format_maps_location_name(raw, "")


def _title_to_business_name(title: str | None) -> str:
    """'SEO Agency Melbourne | Award-Winning…' → 'SEO Agency Melbourne'."""
    t = (title or "").strip()
    if not t:
        return ""
    for sep in (" | ", " – ", " - ", " — "):
        if sep in t:
            return t.split(sep, 1)[0].strip()
    return t[:120]


def _parse_serp_targets(raw: str | None) -> list[dict]:
    """Targets from the Ahrefs SERP chips the user sees in the UI."""
    if not raw or not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for item in data[:_MAX_COMPETITORS]:
        if not isinstance(item, dict):
            continue
        domain = re.sub(r"^www\.", "", str(item.get("domain") or "").strip().lower())
        title = _title_to_business_name(str(item.get("title") or ""))
        name = title or domain
        if not name:
            continue
        pos = item.get("position")
        try:
            organic_rank = int(pos) if pos is not None else None
        except (TypeError, ValueError):
            organic_rank = None
        lp = item.get("local_pack_position")
        try:
            local_pack_position = int(lp) if lp is not None else None
        except (TypeError, ValueError):
            local_pack_position = None
        out.append(
            {
                "title": name,
                "domain": domain or None,
                "organic_rank": organic_rank,
                "maps_rank": None,
                "in_local_pack": bool(item.get("in_local_pack")),
                "local_pack_position": local_pack_position,
            }
        )
    return out


async def _top_maps_competitors(
    session: AsyncSession, client_id: UUID, *, exclude_domain: str
) -> list[dict]:
    """Maps pack from the *latest* scan only (one suburb snapshot — avoids every rival showing #1)."""
    row = (
        await session.execute(
            text(
                """
                SELECT feature_snapshot
                FROM rp_rank_history
                WHERE client_id = :cid AND feature_snapshot IS NOT NULL
                ORDER BY checked_at DESC
                LIMIT 1
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        return []

    snap = row["feature_snapshot"]
    if isinstance(snap, str):
        try:
            snap = json.loads(snap)
        except json.JSONDecodeError:
            return []
    if not isinstance(snap, dict):
        return []

    pack = snap.get("maps_pack")
    if not isinstance(pack, list):
        return []

    out: list[dict] = []
    for item in pack:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        dom = re.sub(r"^www\.", "", str(item.get("domain") or "").strip().lower())
        if not title:
            continue
        if exclude_domain and dom and (
            dom == exclude_domain or exclude_domain in dom or dom in exclude_domain
        ):
            continue
        try:
            rank = int(item.get("rank")) if item.get("rank") is not None else None
        except (TypeError, ValueError):
            rank = None
        out.append(
            {
                "title": title,
                "domain": dom or None,
                "organic_rank": None,
                "maps_rank": rank,
                "in_local_pack": True,
                "local_pack_position": rank,
            }
        )
        if len(out) >= _MAX_COMPETITORS:
            break
    return out


def _parse_post_ts(raw: object) -> datetime | None:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace(" +00:00", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y %H:%M:%S", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _top_terms(texts: list[str], limit: int = 8) -> list[str]:
    """Most frequent meaningful unigrams/bigrams across the posts."""
    uni: Counter[str] = Counter()
    bi: Counter[str] = Counter()
    for t in texts:
        tokens = [
            w for w in re.split(r"[^a-z0-9]+", t.lower())
            if len(w) >= 3 and w not in _TERM_STOPWORDS and not w.isdigit()
        ]
        uni.update(tokens)
        bi.update(f"{a} {b}" for a, b in zip(tokens, tokens[1:]))
    terms: list[str] = [g for g, n in bi.most_common(limit * 2) if n >= 2][:limit]
    if len(terms) < limit:
        covered = {w for g in terms for w in g.split()}
        for w, n in uni.most_common(limit * 3):
            if n >= 2 and w not in covered:
                terms.append(w)
                covered.add(w)
            if len(terms) >= limit:
                break
    return terms


def _analyze_business(
    name: str,
    domain: str | None,
    block: dict | None,
    *,
    keyword: str,
    organic_rank: int | None = None,
    maps_rank: int | None = None,
    in_local_pack: bool = False,
    local_pack_position: int | None = None,
) -> CompetitorGbpPostsItem:
    items = (block or {}).get("items")
    posts_raw = [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []

    kw_low = keyword.lower()
    posts: list[CompetitorGbpPost] = []
    dates: list[datetime] = []
    mentions = 0
    texts: list[str] = []
    for p in posts_raw:
        body = str(p.get("post_text") or p.get("snippet") or "").strip()
        if not body:
            continue
        ts = _parse_post_ts(p.get("timestamp") or p.get("post_date"))
        if ts:
            dates.append(ts)
        has_kw = kw_low in body.lower()
        if has_kw:
            mentions += 1
        texts.append(body)
        posts.append(
            CompetitorGbpPost(
                text=body[:400],
                date=ts.date().isoformat() if ts else None,
                url=str(p.get("url") or "") or None,
                mentions_keyword=has_kw,
            )
        )

    posts_per_month: float | None = None
    first_dt = min(dates) if dates else None
    last_dt = max(dates) if dates else None
    if first_dt and last_dt and len(dates) >= 2:
        span_days = max(1.0, (last_dt - first_dt).days or 1.0)
        posts_per_month = round(len(dates) / (span_days / 30.4), 1)

    return CompetitorGbpPostsItem(
        business_name=name,
        domain=domain,
        organic_rank=organic_rank,
        maps_rank=maps_rank,
        in_local_pack=in_local_pack,
        local_pack_position=local_pack_position,
        posts_count=len(posts),
        first_post_date=first_dt.date().isoformat() if first_dt else None,
        last_post_date=last_dt.date().isoformat() if last_dt else None,
        posts_per_month=posts_per_month,
        keyword_mentions=mentions,
        top_terms=_top_terms(texts),
        recent_posts=posts[:5],
        note=None if posts else "No public GBP posts found for this business.",
    )


async def fetch_competitor_gbp_posts(
    session: AsyncSession,
    client_id: UUID,
    *,
    keyword: str,
    serp_targets: str | None = None,
    force_refresh: bool = False,
) -> CompetitorGbpPostsResponse:
    keyword = " ".join((keyword or "").split()).strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword is required.")

    settings = get_settings()
    if not (settings.dataforseo_login and settings.dataforseo_password):
        return CompetitorGbpPostsResponse(
            keyword=keyword,
            message="Set DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD in backend/.env.",
            source="none",
        )

    profile = (
        await session.execute(
            text("SELECT business_url, metro_label FROM rp_clients WHERE client_id = :cid LIMIT 1"),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    if not profile:
        raise HTTPException(status_code=404, detail="Client not found.")

    from urllib.parse import urlparse

    client_url = str(profile.get("business_url") or "").strip()
    if client_url and not client_url.startswith(("http://", "https://")):
        client_url = "https://" + client_url
    exclude_domain = re.sub(r"^www\.", "", urlparse(client_url).netloc.lower()) if client_url else ""

    metro = str(profile.get("metro_label") or "")
    location_name = _metro_to_location_name(metro)
    city = metro.split(",")[0].strip() if metro else ""

    serp_list = _parse_serp_targets(serp_targets)
    if serp_list:
        competitors = serp_list
        competitor_source = "organic_serp"
    else:
        competitors = await _top_maps_competitors(session, client_id, exclude_domain=exclude_domain)
        competitor_source = "maps_scan"

    if not competitors:
        return CompetitorGbpPostsResponse(
            keyword=keyword,
            competitor_source=competitor_source,
            message=(
                "No organic competitors passed — expand the competitor chips above first, "
                "or run a Maps scan from the Dashboard."
            ),
        )

    async def _posts_block_for(comp: dict, dfs: DataForSEOClient) -> dict | None:
        cache_key = build_cache_key("gbp-updates", "au", comp["title"])
        if not force_refresh:
            cached, _, _ = await get_ahrefs_cache(session, cache_key)
            if cached is not None:
                return cached
        search_kw = f"{comp['title']} {city}".strip() if city else comp["title"]
        block = await dfs.google_business_updates_fetch_block(
            keyword=search_kw,
            location_name=location_name,
            depth=_POST_DEPTH,
        )
        await set_ahrefs_cache(session, cache_key, block or {"items": []}, client_id=client_id)
        return block

    dfs = DataForSEOClient(settings)
    try:
        blocks = await asyncio.gather(
            *(_posts_block_for(c, dfs) for c in competitors),
            return_exceptions=True,
        )
    finally:
        await dfs.aclose()

    items: list[CompetitorGbpPostsItem] = []
    for comp, block in zip(competitors, blocks):
        if isinstance(block, BaseException):
            logger.warning("competitor GBP posts fetch failed for %s: %s", comp["title"], block)
            block = None
        items.append(
            _analyze_business(
                comp["title"],
                comp.get("domain"),
                block,
                keyword=keyword,
                organic_rank=comp.get("organic_rank"),
                maps_rank=comp.get("maps_rank"),
                in_local_pack=bool(comp.get("in_local_pack")),
                local_pack_position=comp.get("local_pack_position"),
            )
        )

    any_posts = any(i.posts_count > 0 for i in items)
    source_note = (
        "Same websites as the organic competitor chips above."
        if competitor_source == "organic_serp"
        else "From your latest Google Maps scan (different list than organic chips)."
    )
    return CompetitorGbpPostsResponse(
        keyword=keyword,
        competitors=items,
        competitor_source=competitor_source,
        source="dataforseo",
        message=(
            None
            if any_posts
            else f"{source_note} None have public GBP posts visible to Google right now."
        ),
    )
