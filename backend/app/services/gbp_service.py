"""GBP Optimiser — read listing state from Google, queue content, health score."""

from __future__ import annotations

import contextlib
import json
import logging
import random
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from uuid6 import uuid7
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.lib.primary_keywords import parse_primary_keywords
from app.services.content_generation_service import (
    _call_claude,
    _get_client_profile,
    _get_top_suburbs,
)
from app.services.gbp_brand_kit_service import get_brand_kit
from app.services.gbp_photos_service import list_gbp_photos

logger = logging.getLogger(__name__)

GBP_LOCATION_READ_MASK = (
    "title,profile,storefrontAddress,categories,websiteUri,regularHours,serviceItems"
)
BI_BASE = "https://mybusinessbusinessinformation.googleapis.com/v1"
GBP_V4_BASE = "https://mybusiness.googleapis.com/v4"
GBP_POST_CHAR_LIMIT = 1500


async def _gbp_integration(session: AsyncSession, client_id: UUID) -> dict | None:
    row = (
        await session.execute(
            text(
                """
                SELECT access_token, refresh_token, extra_data
                FROM rp_integrations
                WHERE client_id = :cid AND type = 'gbp'
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        return None
    if not (str(row.get("access_token") or "").strip() or str(row.get("refresh_token") or "").strip()):
        return None
    extra = row["extra_data"] if isinstance(row["extra_data"], dict) else {}
    if isinstance(row["extra_data"], str):
        try:
            extra = json.loads(row["extra_data"])
        except json.JSONDecodeError:
            extra = {}
    loc = str(extra.get("selected_property") or "").strip()
    if not loc:
        return None
    return {
        "location_name": loc,
        "property_name": str(extra.get("selected_property_name") or "").strip(),
    }


async def _fetch_location(token: str, location_name: str) -> dict:
    from app.routes.v1.integrations import _gbp_google_error_detail

    qs = f"readMask={GBP_LOCATION_READ_MASK}"
    url = f"{BI_BASE}/{location_name}?{qs}"
    async with httpx.AsyncClient(timeout=25) as http:
        resp = await http.get(url, headers={"Authorization": f"Bearer {token}"})
    if not resp.is_success:
        msg = ""
        with contextlib.suppress(Exception):
            msg = str(resp.json().get("error", {}).get("message") or "")
        raise HTTPException(
            status_code=resp.status_code,
            detail=_gbp_google_error_detail(msg, context="GBP location read failed"),
        )
    return resp.json() if isinstance(resp.json(), dict) else {}


async def _fetch_media_count(token: str, location_name: str) -> int:
    url = f"{BI_BASE}/{location_name}/media?pageSize=100"
    async with httpx.AsyncClient(timeout=25) as http:
        resp = await http.get(url, headers={"Authorization": f"Bearer {token}"})
    if not resp.is_success:
        return 0
    data = resp.json() if isinstance(resp.json(), dict) else {}
    items = data.get("mediaItems") or []
    return len(items) if isinstance(items, list) else 0


def _metro_city_name(metro: str) -> str:
    """'Melbourne, VIC' → 'Melbourne'; keeps 'Melbourne CBD' as-is."""
    return (metro or "").strip().split(",")[0].strip()


def _suburb_name_only(suburb_entry: str) -> str:
    """'South Yarra, VIC' → 'South Yarra'."""
    return (suburb_entry or "").strip().split(",")[0].strip()


def _state_from_metro(metro: str) -> str:
    return (metro or "").strip().split(",")[-1].strip().upper() if "," in (metro or "") else ""


_AU_STATES = r"(?:VIC|NSW|QLD|WA|SA|TAS|ACT|NT)"


def _replace_location_repeats(text: str, location: str, replacement: str) -> str:
    """Replace every occurrence of `location` after the first with `replacement`.
    Handles possessives ('s) and trailing state labels (, VIC etc.) gracefully."""
    loc = (location or "").strip()
    if not loc:
        return text

    # Pattern captures optional possessive and optional ", STATE"
    patt = re.compile(
        rf"(\b{re.escape(loc)}\b)("
        rf"(?:'\s*s\b)?"          # optional 's
        rf"(?:\s*,\s*{_AU_STATES})?)",  # optional , VIC
        re.IGNORECASE,
    )
    matches = list(patt.finditer(text or ""))
    if len(matches) <= 1:
        return text

    out = text
    for m in reversed(matches[1:]):
        possessive = m.group(2) or ""
        repl = f"{replacement}'s" if possessive.strip().startswith("'") else replacement
        out = out[: m.start()] + repl + out[m.end() :]

    return re.sub(r"  +", " ", out)


def _strip_location_names(text: str, names: list[str]) -> str:
    """Remove all occurrences of forbidden suburb names (city mode)."""
    out = text or ""
    for name in names:
        n = (name or "").strip()
        if not n:
            continue
        # Remove possessive + optional state
        out = re.sub(
            rf"\b{re.escape(n)}\b(?:'\s*s\b)?(?:\s*,\s*{_AU_STATES})?",
            "",
            out,
            flags=re.IGNORECASE,
        )
    return re.sub(r"  +", " ", out).strip()


def _sanitize_post_locations(
    body: str,
    *,
    location_scope: str,
    location_label: str,
    location_full: str,
    city_name: str,
    target_keyword: str,
    forbidden_names: list[str],
) -> str:
    """Single geographic focus enforcement.

    City mode: strip all suburb names; keep city name exactly once.
    Suburb mode: strip city name (unless in keyword); keep suburb exactly once.
    """
    scope = (location_scope or "suburb").strip().lower()
    text = (body or "").strip()
    if not text:
        return text

    suburb_label = _suburb_name_only(location_full or location_label)
    kw_low = (target_keyword or "").lower()
    local_alt = "the local area"
    local_poss_alt = "the local community"

    if scope == "city":
        # 1. Remove all suburb/grid names entirely
        text = _strip_location_names(text, forbidden_names)
        # 2. Keep city name only once (replace repeats with neutral phrase)
        city_alt = "local businesses"
        text = _replace_location_repeats(text, location_full, city_alt)
        text = _replace_location_repeats(text, city_name, city_alt)

    else:
        # Suburb mode — remove city mentions unless they are inside the Ahrefs keyword
        if city_name and city_name.lower() not in kw_low:
            # Replace "Melbourne, VIC" / "Melbourne" (all forms) with neutral phrases
            city_patt = re.compile(
                rf"\b{re.escape(city_name)}\b(?:'\s*s\b)?(?:\s*,\s*{_AU_STATES})?",
                re.IGNORECASE,
            )
            def _city_repl(m: re.Match) -> str:
                full = m.group(0)
                if "'" in full:
                    return f"{local_poss_alt}'s"
                return local_alt

            text = city_patt.sub(_city_repl, text)
            # Clean up: "the local area team" → "our team"
            text = re.sub(rf"\b{re.escape(city_name)}\s+team\b", "our team", text, flags=re.IGNORECASE)

        # Keep suburb name exactly once — replace later mentions with "the suburb"
        text = _replace_location_repeats(text, location_full, "the suburb")
        text = _replace_location_repeats(text, suburb_label, "the suburb")
        text = _replace_location_repeats(text, location_label, "the suburb")

    # Cleanup
    text = re.sub(r"\bthe area\s+team\b", "our team", text, flags=re.IGNORECASE)
    text = re.sub(r"\bthe suburb\s+team\b", "our team", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"  +", " ", text)
    return text.strip()


def _phrase_occurrences(text: str, phrase: str) -> int:
    """Count phrase matches; single words use word boundaries (not substrings inside other words)."""
    low = (text or "").lower()
    p = re.sub(r"\s+", " ", (phrase or "").strip().lower())
    if not p:
        return 0
    if " " in p:
        return len(re.findall(re.escape(p), low))
    return len(re.findall(rf"\b{re.escape(p)}\b", low))


def _keyword_counts(text: str, keywords: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for kw in keywords:
        k = re.sub(r"\s+", " ", (kw or "").strip())
        if not k:
            continue
        count = _phrase_occurrences(text, k)
        out.append({"keyword": k, "count": count, "present": count > 0})
    return out


def _parse_location_service_names(loc: dict) -> list[str]:
    names: list[str] = []
    for item in loc.get("serviceItems") or []:
        if not isinstance(item, dict):
            continue
        free = item.get("freeFormServiceItem") or item.get("free_form_service_item")
        if isinstance(free, dict):
            label = free.get("label") or {}
            if isinstance(label, dict):
                display = label.get("displayName") or label.get("display_name")
                if display:
                    names.append(str(display).strip())
        structured = item.get("structuredServiceItem") or item.get("structured_service_item")
        if isinstance(structured, dict):
            desc = structured.get("description")
            if desc:
                names.append(str(desc).strip())
    return [n for n in names if n]


def _build_primary_target_keywords(primary: str, metro: str, suburbs: list[str]) -> list[str]:
    """Local-intent phrases for GBP description audit (full keyword + metro/suburb, not single-word fragments)."""
    primary = re.sub(r"\s+", " ", (primary or "").strip())
    if not primary:
        return []

    kws: list[str] = []
    seen: set[str] = set()

    def add(k: str) -> None:
        k = re.sub(r"\s+", " ", (k or "").strip())
        if len(k) < 4:
            return
        key = k.lower()
        if key in seen:
            return
        seen.add(key)
        kws.append(k)

    city = _metro_city_name(metro)
    words = [w for w in primary.split() if w]

    add(primary)

    if city:
        add(f"{primary} {city}")
        add(f"{primary} in {city}")
        if len(words) >= 2:
            add(f"{city} {primary}")

    if len(words) >= 2:
        add(f"{primary} services")

    for sub_entry in suburbs[:4]:
        sub = _suburb_name_only(sub_entry)
        if not sub:
            continue
        if city and sub.lower() == city.lower():
            continue
        add(f"{primary} {sub}")
        add(f"{sub} {primary}")

    return kws[:10]


def _suggested_service_keywords(primary: str, categories: list[str]) -> list[str]:
    """Service names to check on the GBP services list (aligned with primary keyword)."""
    primary = re.sub(r"\s+", " ", (primary or "").strip())
    kws: list[str] = []
    seen: set[str] = set()

    def add(k: str) -> None:
        k = re.sub(r"\s+", " ", (k or "").strip())
        if len(k) < 3:
            return
        key = k.lower()
        if key in seen:
            return
        seen.add(key)
        kws.append(k)

    if not primary:
        return ["Core service", "Consultation"]

    label = primary.title() if primary == primary.lower() else primary
    add(label)
    add(f"Local {label}")

    for cat in categories[1:4]:
        c = (cat or "").strip()
        if c and c.lower() not in primary.lower():
            add(c)

    words = primary.split()
    if len(words) >= 2:
        add(f"{' '.join(w.title() for w in words[:2])} consultation")
    else:
        add(f"{label} consultation")

    trade_low = primary.lower()
    if any(t in trade_low for t in ("plumb", "electric", "locksmith", "hvac", "pest")):
        add(f"Emergency {label}")

    return kws[:6]


def _audit_services_on_gbp(suggested: list[str], on_listing: list[str]) -> list[dict[str, Any]]:
    combined = " ".join(on_listing).lower()
    out: list[dict[str, Any]] = []
    for kw in suggested:
        k = kw.strip()
        if not k:
            continue
        present = any(
            k.lower() in name.lower() or name.lower() in k.lower() for name in on_listing
        ) or k.lower() in combined
        out.append({"keyword": k, "count": 1 if present else 0, "present": present})
    return out


def _keyword_gap_messages(primary: list[dict[str, Any]], services: list[dict[str, Any]]) -> list[str]:
    gaps: list[str] = []
    for item in primary:
        if not item.get("present"):
            gaps.append(
                f'"{item["keyword"]}" not in description — use Generate description, then Approve & publish'
            )
    for item in services:
        if not item.get("present"):
            gaps.append(
                f'"{item["keyword"]}" not in GBP services list — add in Google Business Profile or Services tab'
            )
    return gaps[:8]


def _text_snippet(text: str, max_len: int = 90) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return "—"
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def _audit_present_count(audit: list[dict[str, Any]]) -> tuple[int, int]:
    total = len(audit)
    present = sum(1 for a in audit if a.get("present"))
    return present, total


def _build_keyword_placement_rows(
    *,
    primary_kw: str,
    primary_audit: list[dict[str, Any]],
    service_audit: list[dict[str, Any]],
    targets: list[str],
    categories: list[str],
    gbp_service_names: list[str],
    description_google: str,
    display_description: str,
    desc_draft: dict | None,
    posts: list[dict],
    queue: list[dict],
    photo_count: int,
    connected: bool,
) -> list[dict[str, Any]]:
    """Live placement table — every cell derived from GBP API, queue, or audits."""
    desc_present, desc_total = _audit_present_count(primary_audit)
    svc_present, svc_total = _audit_present_count(service_audit)
    pk_low = primary_kw.lower()

    if desc_draft and desc_draft.get("status") == "pending":
        desc_source = "RankPilot (draft pending)"
    elif description_google:
        desc_source = "Google (live)" if not desc_draft else "Google + RankPilot"
    elif desc_draft:
        desc_source = "RankPilot"
    else:
        desc_source = "Not on listing" if connected else "GBP not connected"

    desc_example = _text_snippet(display_description or description_google)

    primary_cat = categories[0] if categories else ""
    cat_has_kw = bool(primary_cat and pk_low and pk_low in primary_cat.lower())
    if not primary_cat:
        cat_placed = "No category on GBP"
        cat_impact, cat_level = "Missing", "warning"
    elif cat_has_kw:
        cat_placed = f"Primary keyword in “{primary_cat}”"
        cat_impact, cat_level = "Critical", "critical"
    else:
        cat_placed = f"Keyword not in “{primary_cat}”"
        cat_impact, cat_level = "Needs keyword", "warning"

    if gbp_service_names:
        svc_example = _text_snippet(" · ".join(gbp_service_names[:3]))
        svc_created = "Google (live)"
    else:
        svc_example = "No services returned from GBP API"
        svc_created = "Google" if connected else "—"

    posts_with_kw = 0
    latest_post_body = ""
    for p in posts:
        body = str(p.get("body") or "")
        if body and _audit_present_count(_keyword_counts(body, targets))[0] > 0:
            posts_with_kw += 1
        if not latest_post_body and body:
            latest_post_body = body
    post_total = len(posts)
    if post_total == 0:
        post_placed = "0 posts in RankPilot"
        post_created = "—"
        post_impact, post_level = "No posts", "warning"
    else:
        post_placed = f"{posts_with_kw}/{post_total} posts include target keywords"
        post_created = "RankPilot"
        post_impact, post_level = (
            ("Medium", "medium") if posts_with_kw else ("No keywords in posts", "warning")
        )

    qa_items = [q for q in queue if q["content_type"] == "gbp_qa_answer"]
    qa_with_kw = 0
    latest_qa = ""
    for q in qa_items:
        body = str(q.get("body") or "")
        if body and _audit_present_count(_keyword_counts(body, targets))[0] > 0:
            qa_with_kw += 1
        if not latest_qa and body:
            latest_qa = body
    if not qa_items:
        qa_placed = "0 Q&A answers in queue"
        qa_created = "—"
        qa_impact, qa_level = "No Q&A yet", "low"
    else:
        qa_placed = f"{qa_with_kw}/{len(qa_items)} answers include keywords"
        qa_created = "RankPilot"
        qa_impact, qa_level = "Medium" if qa_with_kw else "Needs keywords", "medium" if qa_with_kw else "warning"

    review_items = [q for q in queue if "review" in str(q.get("content_type") or "").lower()]
    if not review_items:
        rev_placed = "0 review responses tracked"
        rev_created = "—"
        rev_impact, rev_level = "Low (indirect)", "low"
        rev_example = "Generate from Reviews module when available"
    else:
        rev_placed = f"{len(review_items)} responses in queue"
        rev_created = "RankPilot"
        rev_impact, rev_level = "Low", "low"
        rev_example = _text_snippet(str(review_items[0].get("body") or ""))

    if photo_count <= 0:
        photo_placed = "0 photos on listing"
        photo_impact, photo_level = "Add photos", "warning"
        photo_example = "—"
    else:
        photo_placed = f"{photo_count} photos on GBP"
        photo_impact, photo_level = "Low (minor signal)", "low"
        slug = re.sub(r"[^a-z0-9]+", "-", primary_kw.lower()).strip("-") or "business"
        photo_example = f"e.g. {slug}-team.jpg (rename via RankPilot — coming soon)"

    if desc_total == 0:
        desc_placed = "Set primary keyword in settings"
        desc_impact, desc_level = "—", "warning"
    elif desc_present == desc_total:
        desc_placed = f"{desc_present}/{desc_total} target phrases found"
        desc_impact, desc_level = "Very high", "very_high"
    elif desc_present > 0:
        desc_placed = f"{desc_present}/{desc_total} target phrases found"
        desc_impact, desc_level = "Good — gaps remain", "high"
    else:
        desc_placed = f"0/{desc_total} phrases in description"
        desc_impact, desc_level = "Generate description", "warning"

    if svc_total == 0:
        svc_placed = "No service targets"
    else:
        svc_placed = f"{svc_present}/{svc_total} service keywords on listing"
    svc_impact, svc_level = (
        ("High", "high") if svc_present >= max(1, svc_total // 2) else ("Gaps in services", "warning")
    )

    rows: list[dict[str, Any]] = [
        {
            "location": "Business Description",
            "keywords_placed": desc_placed,
            "created_in": desc_source,
            "example": desc_example,
            "impact": desc_impact,
            "impact_level": desc_level,
        },
        {
            "location": "Service Category Name",
            "keywords_placed": cat_placed,
            "created_in": "Google (live)" if connected and primary_cat else "—",
            "example": primary_cat or "—",
            "impact": cat_impact,
            "impact_level": cat_level,
        },
        {
            "location": "Services List Names",
            "keywords_placed": svc_placed,
            "created_in": svc_created,
            "example": svc_example,
            "impact": svc_impact,
            "impact_level": svc_level,
        },
        {
            "location": "Weekly Posts",
            "keywords_placed": post_placed,
            "created_in": post_created,
            "example": _text_snippet(latest_post_body),
            "impact": post_impact,
            "impact_level": post_level,
        },
        {
            "location": "Q&A Answers",
            "keywords_placed": qa_placed,
            "created_in": qa_created,
            "example": _text_snippet(latest_qa),
            "impact": qa_impact,
            "impact_level": qa_level,
        },
        {
            "location": "Review Responses",
            "keywords_placed": rev_placed,
            "created_in": rev_created,
            "example": rev_example,
            "impact": rev_impact,
            "impact_level": rev_level,
        },
        {
            "location": "Photo file names",
            "keywords_placed": photo_placed,
            "created_in": "Google (live)" if connected else "—",
            "example": photo_example,
            "impact": photo_impact,
            "impact_level": photo_level,
        },
    ]
    return rows


async def _keyword_audits_for_client(
    session: AsyncSession,
    client_id: UUID,
    profile: dict,
    audit_text: str,
    categories: list[str],
    gbp_service_names: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
    suburbs = await _get_top_suburbs(session, client_id, 4)
    primary_kw = str(profile.get("primary_keyword") or "").strip()
    metro = str(profile.get("metro_label") or "").strip()
    targets = _build_primary_target_keywords(primary_kw, metro, suburbs)
    primary_audit = _keyword_counts(audit_text, targets)
    service_targets = _suggested_service_keywords(primary_kw, categories)
    service_audit = _audit_services_on_gbp(service_targets, gbp_service_names)
    gaps = _keyword_gap_messages(primary_audit, service_audit)
    return primary_audit, service_audit, gaps, targets


def _calculate_health(
    description: str,
    categories_count: int,
    photo_count: int,
    has_recent_post: bool,
) -> tuple[int, list[dict[str, str]]]:
    """Simplified health score aligned with mockup weights (max 100)."""
    desc_len = len(description or "")
    desc_pts = 0
    if desc_len > 200:
        desc_pts += 10
    if desc_len >= 80:
        desc_pts += 10
    desc_pts = min(20, desc_pts)

    cat_pts = 20 if categories_count >= 5 else int((categories_count / 5) * 20)
    photo_pts = min(20, int((photo_count / 10) * 20))
    post_pts = 20 if has_recent_post else 5

    score = min(100, desc_pts + cat_pts + photo_pts + post_pts)
    breakdown = [
        {"label": "Description", "detail": f"{desc_len} chars", "points": desc_pts},
        {"label": "Categories", "detail": f"{categories_count} additional", "points": cat_pts},
        {"label": "Photos", "detail": f"{photo_count} on listing", "points": photo_pts},
        {"label": "Posts", "detail": "Recent activity" if has_recent_post else "No recent post", "points": post_pts},
    ]
    return score, breakdown


async def _queue_items(session: AsyncSession, client_id: UUID) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT id, content_type, status, payload, generated_at, published_at, created_at
                FROM rp_content_queue
                WHERE client_id = :cid
                  AND content_type IN ('gbp_post', 'gbp_description', 'gbp_qa_answer')
                ORDER BY created_at DESC
                LIMIT 50
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().all()
    items: list[dict] = []
    for r in rows:
        payload = r["payload"] if isinstance(r["payload"], dict) else {}
        if isinstance(r["payload"], str):
            try:
                payload = json.loads(r["payload"])
            except json.JSONDecodeError:
                payload = {}
        items.append(
            {
                "id": str(r["id"]),
                "content_type": r["content_type"],
                "status": r["status"],
                "title": payload.get("title") or "",
                "body": payload.get("body") or "",
                "photo_id": payload.get("photo_id"),
                "photo_url": payload.get("photo_url"),
                "image_note": payload.get("image_note"),
                "target_keyword": payload.get("target_keyword"),
                "scheduled_for": payload.get("scheduled_for"),
                "char_count": payload.get("char_count"),
                "keywords_used": payload.get("keywords_used"),
                "generated_at": r["generated_at"].isoformat() if r["generated_at"] else None,
                "published_at": r["published_at"].isoformat() if r["published_at"] else None,
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
        )
    return items


def _description_queue_slice(queue: list[dict]) -> tuple[list[dict], dict | None]:
    """All GBP descriptions (newest first) and the active editable draft, if any."""
    descriptions = [q for q in queue if q["content_type"] == "gbp_description"]
    active = next((d for d in descriptions if d["status"] in ("pending", "approved")), None)
    return descriptions, active


async def get_gbp_overview(session: AsyncSession, client_id: UUID) -> dict:
    intg = await _gbp_integration(session, client_id)
    profile = await _get_client_profile(session, client_id)
    queue = await _queue_items(session, client_id)

    primary_kw = str(profile.get("primary_keyword") or "local business").strip()

    if not intg:
        primary_audit, service_audit, gaps, targets = await _keyword_audits_for_client(
            session, client_id, profile, "", [], []
        )
        posts = [q for q in queue if q["content_type"] == "gbp_post"]
        description_history, desc_draft = _description_queue_slice(queue)
        draft_body = (desc_draft["body"] if desc_draft else "") or ""
        placement = _build_keyword_placement_rows(
            primary_kw=primary_kw,
            primary_audit=primary_audit,
            service_audit=service_audit,
            targets=targets,
            categories=[],
            gbp_service_names=[],
            description_google="",
            display_description=draft_body,
            desc_draft=desc_draft,
            posts=posts,
            queue=queue,
            photo_count=0,
            connected=False,
        )
        return {
            "connected": False,
            "location_name": None,
            "business_name": profile.get("business_name") or "",
            "health_score": None,
            "health_breakdown": [],
            "description": None,
            "description_google": None,
            "description_live": False,
            "primary_keyword": primary_kw,
            "keyword_targets": targets,
            "keyword_placement": placement,
            "keyword_audit": primary_audit,
            "keyword_audit_primary": primary_audit,
            "keyword_audit_services": service_audit,
            "keyword_gaps": gaps,
            "gbp_services_on_listing": [],
            "photo_count": 0,
            "categories": [],
            "weekly_post": None,
            "posts": posts,
            "description_draft": desc_draft,
            "description_history": description_history,
            "activity": _activity_from_queue(queue),
            "library_photos": await list_gbp_photos(session, client_id),
            "brand_kit": await get_brand_kit(session, client_id),
        }

    from app.routes.v1.integrations import _get_google_access_token

    token = await _get_google_access_token(session, client_id, "gbp")
    loc_name = intg["location_name"]
    try:
        loc = await _fetch_location(token, loc_name)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("GBP location fetch failed")
        raise HTTPException(status_code=502, detail=f"GBP location fetch failed: {exc!s}") from exc

    photo_count = await _fetch_media_count(token, loc_name)
    try:
        await sync_gbp_posts_with_google(session, client_id)
        queue = await _queue_items(session, client_id)
    except Exception as exc:
        logger.warning("GBP post sync skipped on overview: %s", exc)

    description = ""
    prof = loc.get("profile")
    if isinstance(prof, dict):
        description = str(prof.get("description") or "").strip()

    cats = loc.get("categories") or {}
    add_cats = []
    if isinstance(cats, dict):
        primary = cats.get("primaryCategory") or cats.get("primary_category")
        if isinstance(primary, dict):
            add_cats.append(str(primary.get("displayName") or primary.get("name") or "Primary"))
        for ac in cats.get("additionalCategories") or cats.get("additional_categories") or []:
            if isinstance(ac, dict):
                add_cats.append(str(ac.get("displayName") or ac.get("name") or ""))

    posts = [q for q in queue if q["content_type"] == "gbp_post"]
    has_recent = any(p["status"] in ("published", "approved") for p in posts)
    health_score, health_breakdown = _calculate_health(
        description, max(0, len(add_cats) - 1), photo_count, has_recent
    )

    weekly = next((p for p in posts if p["status"] in ("pending", "approved")), None)

    description_history, desc_draft = _description_queue_slice(queue)
    description_live = bool(description)
    draft_body = (desc_draft["body"] if desc_draft else "") or ""
    display_description = (
        draft_body
        if desc_draft and desc_draft["status"] in ("pending", "approved")
        else (description or draft_body)
    )

    gbp_services = _parse_location_service_names(loc)
    categories = [c for c in add_cats if c]
    live_text = (description or "").strip()
    primary_audit_live, service_audit, gaps_live, targets = await _keyword_audits_for_client(
        session,
        client_id,
        profile,
        live_text,
        categories,
        gbp_services,
    )
    primary_audit = primary_audit_live
    gaps = gaps_live
    primary_audit_draft: list[dict[str, Any]] | None = None
    gaps_draft: list[str] | None = None
    if draft_body.strip():
        primary_audit_draft, _, gaps_draft, _ = await _keyword_audits_for_client(
            session,
            client_id,
            profile,
            draft_body.strip(),
            categories,
            gbp_services,
        )
        if desc_draft and desc_draft["status"] == "pending":
            primary_audit = primary_audit_draft
            gaps = gaps_draft
    placement = _build_keyword_placement_rows(
        primary_kw=primary_kw,
        primary_audit=primary_audit,
        service_audit=service_audit,
        targets=targets,
        categories=categories,
        gbp_service_names=gbp_services,
        description_google=description,
        display_description=display_description,
        desc_draft=desc_draft,
        posts=posts,
        queue=queue,
        photo_count=photo_count,
        connected=True,
    )

    return {
        "connected": True,
        "location_name": intg.get("property_name") or str(loc.get("title") or ""),
        "business_name": profile.get("business_name") or str(loc.get("title") or ""),
        "health_score": health_score,
        "health_breakdown": health_breakdown,
        "description": display_description,
        "description_google": description,
        "description_live": description_live,
        "primary_keyword": primary_kw,
        "keyword_targets": targets,
        "keyword_placement": placement,
        "keyword_audit": primary_audit,
        "keyword_audit_primary": primary_audit,
        "keyword_audit_live": primary_audit_live,
        "keyword_audit_draft": primary_audit_draft,
        "keyword_audit_services": service_audit,
        "keyword_gaps": gaps,
        "keyword_gaps_live": gaps_live,
        "keyword_gaps_draft": gaps_draft,
        "gbp_services_on_listing": gbp_services,
        "photo_count": photo_count,
        "categories": categories,
        "weekly_post": weekly,
        "posts": posts,
        "description_draft": desc_draft,
        "description_history": description_history,
        "activity": _activity_from_queue(queue),
        "website_uri": str(loc.get("websiteUri") or ""),
        "library_photos": await list_gbp_photos(session, client_id),
        "brand_kit": await get_brand_kit(session, client_id),
    }


def _activity_from_queue(queue: list[dict]) -> list[dict]:
    activity: list[dict] = []
    for q in queue:
        ts = q.get("published_at") or q.get("generated_at") or q.get("created_at")
        if not ts:
            continue
        activity.append(
            {
                "type": q["content_type"],
                "description": q.get("title") or q["content_type"].replace("_", " "),
                "occurred_at": ts,
                "status": q["status"],
            }
        )
    return activity[:20]


async def _recent_post_openings(session: AsyncSession, client_id: UUID, limit: int = 5) -> list[str]:
    """Short snippets from past GBP posts so Claude avoids repeating the same hook."""
    rows = (
        await session.execute(
            text(
                """
                SELECT payload->>'body' AS body
                FROM rp_content_queue
                WHERE client_id = :cid AND content_type = 'gbp_post'
                ORDER BY created_at DESC
                LIMIT :lim
                """
            ),
            {"cid": str(client_id), "lim": limit},
        )
    ).mappings().all()
    out: list[str] = []
    for r in rows:
        body = str(r.get("body") or "").strip()
        if not body:
            continue
        first_line = body.split("\n", 1)[0].strip()[:160]
        if first_line:
            out.append(first_line)
    return out


def _parse_comma_prompts(raw: str | None, limit: int) -> list[str]:
    """Split prompts by newline first, then comma — whichever the user used."""
    if not (raw or "").strip():
        return []
    text = (raw or "").strip()
    if "\n" in text:
        parts = [p.strip() for p in text.splitlines() if p.strip()]
    else:
        parts = [p.strip() for p in text.split(",") if p.strip()]
    return parts[:limit]


def _parse_post_prompt_slots(raw: str | None, limit: int) -> list[str | None]:
    """One slot per post — preserves empty lines and multi-line prompts."""
    if not (raw or "").strip():
        return [None] * limit
    text = raw or ""
    if "<<<POST_SLOT>>>" in text:
        parts = text.split("<<<POST_SLOT>>>")
        slots: list[str | None] = []
        for i in range(limit):
            if i < len(parts):
                s = parts[i].strip()
                slots.append(s if s else None)
            else:
                slots.append(None)
        return slots
    if "\n" in text:
        lines = text.split("\n")
        slots = []
        for i in range(limit):
            if i < len(lines):
                s = lines[i].strip()
                slots.append(s if s else None)
            else:
                slots.append(None)
        return slots
    parts = [p.strip() for p in text.split(",") if p.strip()]
    slots = [None] * limit
    for i, part in enumerate(parts[:limit]):
        slots[i] = part
    return slots


def _parse_structured_prompt_slot(raw: str) -> tuple[str | None, str | None, str | None]:
    """Parse AI-generated slot: image prompt + optional post angle + KEYWORD footer."""
    text = (raw or "").strip()
    if not text:
        return None, None, None

    keyword: str | None = None
    post_angle: str | None = None
    kw_match = re.search(r"(?:^|\n)KEYWORD:\s*(.+?)\s*$", text, re.I | re.M)
    if kw_match:
        keyword = kw_match.group(1).strip().split("\n")[0].strip()
        text = text[: kw_match.start()].strip()

    angle_match = re.search(
        r"(?:^|\n)Post angle(?:\s*\(for copy\))?:\s*(.+?)\s*(?:\n|$)",
        text,
        re.I | re.M,
    )
    if angle_match:
        post_angle = angle_match.group(1).strip()
        text = (text[: angle_match.start()] + text[angle_match.end() :]).strip()
        text = re.sub(r"\n---+\s*$", "", text).strip()

    image_prompt = text.strip() or None
    return keyword, image_prompt, post_angle


def _resolve_target_keyword_from_prompt(
    user_prompt: str | None,
    ahrefs_kws: list[str],
    fallback: str,
) -> tuple[str, str | None]:
    """Map a user prompt slot to (target_keyword, creative_direction).

    When the user clicks an Ahrefs keyword in the UI it lands in the prompt field.
    That value must become target_keyword — not the first unrelated Ahrefs phrase.
    Structured slots from AI prompt gen use KEYWORD: footer lines.
    """
    raw = (user_prompt or "").strip()
    if not raw:
        return fallback, None

    parsed_kw, image_prompt, post_angle = _parse_structured_prompt_slot(raw)
    if parsed_kw:
        direction = post_angle or image_prompt
        ahrefs_by_lower = {k.lower(): k for k in ahrefs_kws if (k or "").strip()}
        target = ahrefs_by_lower.get(parsed_kw.lower(), parsed_kw)
        return target, direction

    ahrefs_by_lower = {k.lower(): k for k in ahrefs_kws if (k or "").strip()}

    if raw.lower() in ahrefs_by_lower:
        return ahrefs_by_lower[raw.lower()], None

    if "," in raw:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        matched = next((p for p in reversed(parts) if p.lower() in ahrefs_by_lower), None)
        if matched:
            kw = ahrefs_by_lower[matched.lower()]
            direction_parts = [p for p in parts if p.lower() != kw.lower()]
            direction = ", ".join(direction_parts).strip() or None
            return kw, direction
        if len(parts) >= 2:
            return parts[-1], ", ".join(parts[:-1]).strip() or None

    for kw in sorted(ahrefs_kws, key=len, reverse=True):
        if kw and kw.lower() in raw.lower():
            direction = re.sub(re.escape(kw), "", raw, flags=re.I).strip(" ,.-")
            return kw, direction or None

    # Short phrase without sentence punctuation — treat as the chosen keyword.
    if len(raw) <= 100 and not re.search(r"[.!?]", raw):
        return raw, None

    return fallback, raw


_BATCH_ANGLE_VARIANTS: list[tuple[str, str]] = [
    ("focus on a customer pain point — what problem does this solve?",
     "open with a pain or struggle, then show how the business fixes it"),
    ("focus on a quick-win tip — what simple action delivers immediate results?",
     "open with a surprising stat or 'most businesses don't know' line"),
    ("focus on social proof / credibility — reviews, results, trust signals",
     "open with a bold claim backed by evidence, then 3 trust-building tips"),
    ("focus on a before/after transformation story",
     "open with a contrast (before vs after), then actionable steps"),
    ("focus on a seasonal or timely angle — why this matters right now",
     "open with a question about what's changing in the industry"),
    ("focus on common myths or misconceptions",
     "open with a myth-bust line, then explain the truth with practical tips"),
    ("focus on ROI — how does this save or make money?",
     "open with a dollar-impact hook, then 3 specific ways to improve ROI"),
    ("focus on the 'how it works' explainer — demystify the process",
     "open with 'here's what actually happens' framing, then step-by-step"),
    ("focus on why competitors fail — what makes this business different?",
     "open with a differentiator hook, then comparison tips"),
    ("focus on a call-to-action urgency angle — why act now?",
     "open with a deadline or limited-offer framing, then action steps"),
]


def _expand_directions_for_batch(
    directions: list[str | None],
    keywords: list[str],
    post_count: int,
    location_label: str,
) -> list[str]:
    """Ensure every post in a batch has a *distinct* direction.

    If the user supplied fewer prompts than post_count, remaining posts get
    auto-generated angle variants derived from the first prompt (or keyword).
    """
    base = next((d for d in directions if d), "") or ""

    result: list[str] = []
    for i in range(post_count):
        existing = directions[i] if i < len(directions) else None
        if existing:
            result.append(existing)
            continue

        kw = keywords[i] if i < len(keywords) else (keywords[-1] if keywords else "")
        variant_idx = i % len(_BATCH_ANGLE_VARIANTS)
        focus, opening = _BATCH_ANGLE_VARIANTS[variant_idx]
        if base:
            direction = (
                f"Based on this theme: '{base[:200]}' — for this post specifically {focus}. "
                f"Structure: {opening}. "
                f"Use the Ahrefs keyword '{kw}' naturally."
            )
        else:
            direction = (
                f"Write a post about '{kw}' for {location_label}: {focus}. "
                f"Structure: {opening}."
            )
        result.append(direction)
    return result


async def _resolve_content_area(
    session: AsyncSession,
    client_id: UUID,
    profile: dict,
) -> tuple[str, str]:
    """(area label for prompts, location_scope)."""
    scope = str(profile.get("location_scope") or "suburb").strip().lower()
    metro = str(profile.get("metro_label") or "").strip()
    city = _metro_city_name(metro)
    state = _state_from_metro(metro)

    if scope == "city":
        if city and state:
            return f"{city}, {state}", "city"
        return city or metro or "your city", "city"

    anchor = str(profile.get("primary_suburb") or "").strip()
    if anchor:
        return (f"{anchor}, {state}" if state else anchor), "suburb"

    suburbs = await _get_top_suburbs(session, client_id, 1)
    if suburbs:
        return suburbs[0], "suburb"
    return metro or "your area", "suburb"


async def _build_location_context(
    session: AsyncSession,
    client_id: UUID,
    profile: dict,
) -> dict[str, Any]:
    """Single geographic focus for GBP post prompts and cleanup."""
    area_full, scope = await _resolve_content_area(session, client_id, profile)
    metro = str(profile.get("metro_label") or "").strip()
    city_name = _metro_city_name(metro)
    state = _state_from_metro(metro)
    label = _suburb_name_only(area_full) if scope == "suburb" else (city_name or _suburb_name_only(area_full))

    forbidden: list[str] = []
    if scope == "city":
        grid = await _get_top_suburbs(session, client_id, 25)
        forbidden = [_suburb_name_only(s) for s in grid]
        anchor = str(profile.get("primary_suburb") or "").strip()
        if anchor:
            forbidden.append(anchor)

    return {
        "scope": scope,
        "area_full": area_full,
        "label": label,
        "city_name": city_name,
        "state": state,
        "forbidden_names": [n for n in dict.fromkeys(forbidden) if n],
    }


async def _areas_for_batch_posts(
    session: AsyncSession,
    client_id: UUID,
    profile: dict,
    count: int,
) -> list[str]:
    """Same area for every post — matches Business Setup (city OR chosen suburb)."""
    area, _ = await _resolve_content_area(session, client_id, profile)
    return [area] * count


async def _ahrefs_keywords_for_posts(
    session: AsyncSession,
    client_id: UUID,
    profile: dict,
    limit: int,
) -> list[str]:
    """Top Ahrefs keyword phrases for GBP post generation (city or suburb scope)."""
    scope = str(profile.get("location_scope") or "suburb").strip().lower()
    city = _metro_city_name(str(profile.get("metro_label") or ""))
    try:
        from app.services.keyword_research_service import fetch_suburb_keyword_research

        research = await fetch_suburb_keyword_research(
            session, client_id, suburb_limit=10, idea_limit=25, force_refresh=False
        )
        kws: list[str] = []
        seen: set[str] = set()

        def add(kw: str) -> None:
            key = kw.strip().lower()
            if not key or key in seen:
                return
            seen.add(key)
            kws.append(kw.strip())

        if research.top_keywords:
            for row in research.top_keywords:
                add(str(row.keyword or ""))
        else:
            phrases = sorted(
                research.suburb_phrases or [],
                key=lambda x: int(x.opportunity_score or 0),
                reverse=True,
            )
            ideas = sorted(
                research.related_ideas or [],
                key=lambda x: int(x.opportunity_score or 0),
                reverse=True,
            )
            for row in phrases:
                add(str(row.keyword or ""))
            for row in ideas:
                add(str(row.keyword or ""))
        if scope == "city" and city:
            city_kws = [k for k in kws if city.lower() in k.lower()]
            if city_kws:
                kws = city_kws
        elif scope == "suburb":
            area_full, _ = await _resolve_content_area(session, client_id, profile)
            suburb = _suburb_name_only(area_full)
            if suburb:
                suburb_kws = [k for k in kws if suburb.lower() in k.lower()]
                if suburb_kws:
                    kws = suburb_kws
                elif city:
                    non_city = [k for k in kws if city.lower() not in k.lower()]
                    if non_city:
                        kws = non_city
        return kws[: max(limit, 10)]
    except Exception as exc:
        logger.warning("Ahrefs keywords skipped for GBP posts: %s", exc)
        return []


_GBP_STRUCTURE_HINTS = [
    "STRUCTURE: Open with a relatable customer problem, then how you solve it, end with a clear call-to-action.",
    "STRUCTURE: Open with a quick local tip or insight, then tie it to your service, end with an invitation to get in touch.",
    "STRUCTURE: Lead with a benefit or result customers get, back it with one concrete detail, close with a call-to-action.",
    "STRUCTURE: Start with a short question your customers ask, answer it, then point them to your service.",
    "STRUCTURE: Open with a seasonal or timely angle, connect it to what you offer, finish with a call-to-action.",
    "STRUCTURE: Highlight what makes you different, give one proof point, end with a friendly invitation.",
]


def _gbp_structure_hint(post_index: int) -> str:
    """Rotate post structures so batch posts don't all read the same way."""
    return _GBP_STRUCTURE_HINTS[(max(1, post_index) - 1) % len(_GBP_STRUCTURE_HINTS)]


def _summarize_post_for_batch(body: str, target_keyword: str, direction: str | None) -> str:
    """Build a one-line summary of a generated post so later posts in the batch can avoid repeating it."""
    opening = (body or "").strip().split("\n", 1)[0].strip()
    opening = re.sub(r"\s+", " ", opening)[:120]
    angle = (direction or "").strip()
    angle = re.sub(r"\s+", " ", angle)[:80]
    parts = [f"keyword '{target_keyword}'"]
    if angle:
        parts.append(f"angle: {angle}")
    if opening:
        parts.append(f"opening: \"{opening}\"")
    return " — ".join(parts)


async def _generate_one_gbp_post(
    session: AsyncSession,
    client_id: UUID,
    *,
    target_keyword: str,
    area: str,
    location_ctx: dict[str, Any],
    user_direction: str | None,
    profile: dict,
    brand: dict,
    settings: Any,
    recent_hooks: list[str],
    post_index: int,
    post_total: int,
    prior_batch_summaries: list[str] | None = None,
    prior_archetypes: list[str] | None = None,
) -> dict:
    from app.services.gbp_photos_service import generate_post_image_from_content

    keyword = str(profile.get("primary_keyword") or "services").strip()
    bname = str(profile.get("business_name") or "Your business").strip()
    brand_voice = str(brand.get("brand_voice") or "").strip()
    forbidden = str(brand.get("forbidden_words") or "").strip()

    location_scope = str(location_ctx.get("scope") or "suburb")
    location_label = str(location_ctx.get("label") or _suburb_name_only(area))
    location_full = str(location_ctx.get("area_full") or area)
    city_name = str(location_ctx.get("city_name") or "")
    forbidden_names: list[str] = list(location_ctx.get("forbidden_names") or [])

    has_user_direction = bool((user_direction or "").strip())
    direction = (user_direction or "").strip()
    if not direction:
        direction = (
            f"Create a unique angle for the Ahrefs keyword '{target_keyword}' — "
            f"local tips, customer pain points, or timely advice for {location_label}."
        )

    avoid_block = ""
    if recent_hooks:
        avoid_block = "\n".join(f"- {h}" for h in recent_hooks[:8])
        avoid_block = f"\nDo NOT reuse these past opening lines or the same angle:\n{avoid_block}\n"

    if prior_batch_summaries:
        prior_block = "\n".join(f"- {s}" for s in prior_batch_summaries[:8])
        avoid_block += (
            f"\nThese posts were already generated in THIS batch — your post MUST cover a "
            f"different angle, topic, and opening:\n{prior_block}\n"
        )

    voice_line = f"Brand voice: {brand_voice}\n" if brand_voice else ""
    forbid_line = f"Never use these words/claims: {forbidden}\n" if forbidden else ""
    batch_line = f"Post {post_index} of {post_total} in a batch — must be distinct from the others.\n" if post_total > 1 else ""

    if location_scope == "city":
        forbid_places = ", ".join(forbidden_names[:12]) if forbidden_names else "any suburb names"
        location_rules = (
            f"LOCATION: City-wide — {location_full} only.\n"
            f"Never name suburbs ({forbid_places}).\n"
        )
        locals_phrase = f"local businesses in {location_label}"
    else:
        location_rules = (
            f"LOCATION: Suburb — {location_full} only.\n"
            f"Do not also mention the city ({city_name}) unless it appears inside the Ahrefs keyword phrase.\n"
        )
        locals_phrase = f"people in {location_label}"

    location_once_rule = (
        f"Use the place name '{location_label}' at most ONCE in the entire post "
        f"(the Ahrefs keyword counts as that mention if it already contains the location).\n"
        f"Do not repeat the same city or suburb. Never combine suburb and city in one post.\n"
    )

    if has_user_direction:
        # The user's prompt is the SUBJECT of the post — it must drive the content.
        topic_block = (
            f"WRITE THE POST ABOUT THIS EXACT TOPIC (this is the most important instruction — "
            f"the whole post must be about this, not a generic marketing post):\n"
            f">>> {direction} <<<\n\n"
            f"Treat the above as the subject, angle, and message of the post. "
            f"Do NOT default to a generic 'most businesses lose visitors' style post. "
            f"Write specifically about what is described above.\n"
        )
    else:
        # No user prompt — fall back to a rotating structure so auto-posts stay varied.
        topic_block = (
            f"USER DIRECTION — this post's unique topic and angle (follow closely, do not generalise):\n"
            f"{direction}\n\n"
            f"{_gbp_structure_hint(post_index)}\n"
        )

    # Small random nudge so two generations with the same prompt are never identical.
    variety_nudge = random.choice(
        [
            "Open with a fresh, unexpected hook.",
            "Start with a short question.",
            "Lead with a concrete example or mini scenario.",
            "Begin with a surprising fact or insight.",
            "Open with a direct, confident statement.",
            "Start with a relatable everyday moment.",
        ]
    )

    prompt = (
        f"Write a Google Business Profile post (160–200 words, max {GBP_POST_CHAR_LIMIT} characters) for:\n\n"
        f"Business: {bname}\n"
        f"Primary service: {keyword}\n"
        f"Target Ahrefs keyword (include exactly once, naturally): {target_keyword}\n"
        f"{location_rules}"
        f"{location_once_rule}"
        f"{voice_line}"
        f"{forbid_line}"
        f"{batch_line}\n"
        f"{topic_block}\n"
        f"{variety_nudge}\n\n"
        f"RULES:\n"
        f"- Hard limit: {GBP_POST_CHAR_LIMIT} characters total\n"
        f"- Say 'our team' instead of '{city_name} team' or '{location_label} team'\n"
        f"- Use unique phrasing; avoid clichés\n"
        f"- Plain text only (emoji + bullets with • or -). No markdown headers.\n"
        f"{avoid_block}"
    )
    logger.info(
        "GBP post %d/%d — scope=%s area=%s keyword=%s",
        post_index, post_total, location_scope, location_full, target_keyword,
    )
    raw_body = _call_claude(
        prompt,
        settings.anthropic_api_key,
        max_tokens=4096,
        temperature=0.95,
    ).strip()
    raw_body = _sanitize_post_locations(
        raw_body,
        location_scope=location_scope,
        location_label=location_label,
        location_full=location_full,
        city_name=city_name,
        target_keyword=target_keyword,
        forbidden_names=forbidden_names,
    )
    body = normalize_gbp_post_body(raw_body, api_key=settings.anthropic_api_key)

    image_note = ""
    photo_id = None
    photo_url = None
    img = await generate_post_image_from_content(
        session,
        client_id,
        body,
        business_name=bname,
        keyword=target_keyword,
        metro=str(profile.get("metro_label") or area),
        theme=direction,
        brand_config=brand,
        post_index=post_index,
        post_total=post_total,
        prior_archetypes=prior_archetypes,
    )
    if img:
        photo_id = img.get("photo_id")
        photo_url = img.get("url")
        image_note = (
            f"AI image generated for this post (Runway, {img.get('archetype', 'creative')} style)."
        )
    elif not (settings.runwayml_api_key or "").strip():
        image_note = "No post image — set RUNWAYML_API_KEY to auto-generate photos with posts."
    else:
        image_note = "Post text created; image generation failed or was skipped."

    now = datetime.now(UTC)
    post_id = str(uuid7())
    title = (
        f"GBP post {post_index}/{post_total} — {target_keyword}"
        if post_total > 1
        else f"Weekly post — {bname}"
    )
    await session.execute(
        text(
            """
            INSERT INTO rp_content_queue
                (id, client_id, content_type, status, approval_mode,
                 payload, generated_at, created_at, updated_at)
            VALUES
                (:id, :cid, 'gbp_post', 'pending', 'approval_required',
                 (CAST(:payload AS text))::jsonb, :now, :now, :now)
            """
        ),
        {
            "id": post_id,
            "cid": str(client_id),
            "now": now,
            "payload": json.dumps({
                "title": title,
                "body": body,
                "word_count": len(body.split()),
                "tags": ["STANDARD", target_keyword, area],
                "target_keyword": target_keyword,
                "photo_id": photo_id,
                "photo_url": photo_url,
                "image_note": image_note,
                "generation_prompt": direction[:500] if direction else None,
                "batch_index": post_index,
                "batch_total": post_total,
                "location_scope": location_scope,
                "target_area": location_full,
            }),
        },
    )
    opening = body.split("\n", 1)[0].strip()[:160]
    if opening:
        recent_hooks.insert(0, opening)

    batch_summary = _summarize_post_for_batch(body, target_keyword, direction)

    return {
        "id": post_id,
        "title": title,
        "body": body,
        "status": "pending",
        "target_keyword": target_keyword,
        "photo_id": photo_id,
        "photo_url": photo_url,
        "image_note": image_note,
        "image_archetype": img.get("archetype") if img else None,
        "batch_summary": batch_summary,
    }


def _pick_diverse_keywords(kws: list[str], n: int) -> list[str]:
    """Return *n* keywords cycling through *kws* so each post gets a distinct keyword."""
    if not kws:
        return [""] * n
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for k in kws:
        if k not in seen:
            seen.add(k)
            unique.append(k)
    # Cycle through unique keywords to fill n slots
    return [unique[i % len(unique)] for i in range(n)]


_GBP_DM_ANGLES: list[str] = [
    "SEO and organic search visibility",
    "Google Ads / PPC campaign ROI",
    "Social media marketing and engagement",
    "Content marketing and blog strategy",
    "Email marketing and nurture sequences",
    "Local SEO and Google Maps visibility",
    "Website conversion rate optimization",
    "Analytics and data-driven marketing",
    "Brand awareness and storytelling",
    "Online reputation and review management",
    "Video marketing and YouTube presence",
    "Marketing automation and lead generation",
]


def _fallback_gbp_direction(keyword: str, index: int) -> str:
    angle = _GBP_DM_ANGLES[index % len(_GBP_DM_ANGLES)]
    return f"Write about {angle} for local businesses, {keyword}"


def _parse_openai_json_content(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _extract_openrouter_text(data: dict) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    msg = first.get("message") if isinstance(first, dict) else None
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    txt = item.get("text")
                    if isinstance(txt, str) and txt.strip():
                        parts.append(txt.strip())
                elif isinstance(item, str) and item.strip():
                    parts.append(item.strip())
            if parts:
                return " ".join(parts).strip()
    txt = first.get("text") if isinstance(first, dict) else None
    if isinstance(txt, str) and txt.strip():
        return txt.strip()
    return ""


async def _call_openrouter_text(
    *,
    api_key: str,
    model: str,
    system: str,
    user: str,
    temperature: float = 0.7,
    max_tokens: int = 1200,
) -> str:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=90) as http:
        resp = await http.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "HTTP-Referer": str(settings.google_redirect_base_url or "http://localhost:5173"),
                "X-Title": "RankPilot GBP",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )

    if not resp.is_success:
        detail = resp.text[:300]
        with contextlib.suppress(Exception):
            err = resp.json()
            if isinstance(err, dict):
                detail = str(err.get("error", {}).get("message") or detail)
        raise HTTPException(status_code=502, detail=f"OpenRouter error: {detail}")

    data = resp.json()
    content = _extract_openrouter_text(data if isinstance(data, dict) else {})
    if not content:
        raise HTTPException(status_code=502, detail="OpenRouter returned empty content.")
    return content.strip()


async def _call_openrouter_json(
    *,
    api_key: str,
    model: str,
    system: str,
    user: str,
    temperature: float = 0.85,
    max_tokens: int = 4096,
) -> str:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=90) as http:
        resp = await http.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "HTTP-Referer": str(settings.google_redirect_base_url or "http://localhost:5173"),
                "X-Title": "RankPilot GBP",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            },
        )

    if not resp.is_success:
        detail = resp.text[:300]
        with contextlib.suppress(Exception):
            err = resp.json()
            if isinstance(err, dict):
                detail = str(err.get("error", {}).get("message") or detail)
        raise HTTPException(status_code=502, detail=f"OpenRouter error: {detail}")

    data = resp.json()
    content = _extract_openrouter_text(data if isinstance(data, dict) else {})
    if not content:
        raise HTTPException(status_code=502, detail="OpenRouter returned empty content.")
    return content


async def generate_gbp_post_directions(
    session: AsyncSession,
    client_id: UUID,
    *,
    count: int = 1,
    keywords: list[str],
) -> dict:
    """Use OpenRouter (GPT-4o mini) to draft post direction slots from selected Ahrefs keywords."""
    from app.core.config import get_openrouter_api_key, get_openrouter_prompt_model

    api_key = get_openrouter_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY is not configured.")

    prompt_count = max(1, min(int(count), 10))
    selected = [re.sub(r"\s+", " ", k.strip()) for k in keywords if (k or "").strip()]
    if not selected:
        raise HTTPException(status_code=400, detail="Select at least one Ahrefs keyword.")

    profile = await _get_client_profile(session, client_id)
    brand = await get_brand_kit(session, client_id)
    location_ctx = await _build_location_context(session, client_id, profile)

    bname = str(profile.get("business_name") or "Your business").strip()
    brand_voice = str(brand.get("brand_voice") or "").strip()
    location_label = str(location_ctx.get("area_full") or location_ctx.get("label") or "your area")
    assigned_keywords = _pick_diverse_keywords(selected, prompt_count)
    primary_colour = str(brand.get("primary_color") or "#2E8B7F").strip()
    secondary_colour = str(brand.get("secondary_color") or "#1A1A2E").strip()
    archetypes_list = "SOCIAL_PROOF, AUTHORITY, URGENCY, PROBLEM_SOLVE, OFFER, DATA_DRIVEN"

    user_prompt = (
        f"Generate exactly {prompt_count} detailed Google Business Profile IMAGE generation briefs "
        f"for a digital marketing agency. Each brief must be a deep, persuasive Runway/Midjourney-style "
        f"photo prompt — NOT a one-line tagline.\n\n"
        f"Business: {bname}\n"
        f"Location focus: {location_label}\n"
        f"Brand voice: {brand_voice or 'professional, persuasive, local expert'}\n"
        f"Brand colours: primary {primary_colour}, secondary {secondary_colour}\n\n"
        f"Keyword assignment (use EXACTLY one per prompt, in order):\n"
        + "\n".join(f"{i + 1}. {kw}" for i, kw in enumerate(assigned_keywords))
        + f"\n\nRotate these AD ARCHETYPES (one per prompt, never repeat in this batch): "
        f"{archetypes_list}.\n\n"
        "Digital marketing topics to cover across the batch (each prompt different): "
        + ", ".join(_GBP_DM_ANGLES[:10])
        + ".\n\n"
        "Return JSON only:\n"
        '{"prompts":[{"keyword":"exact keyword","archetype":"SOCIAL_PROOF|...","post_angle":"2 sentences for GBP post copy",'
        '"image_prompt":"FULL detailed image prompt — see rules below"}]}\n\n'
        "image_prompt RULES (150–280 words each, persuasive and specific):\n"
        "- Open with: Create a unique, professional Google Business Profile post photo for {business}...\n"
        "- Include sections: CORE KEYWORD, VISUAL HOOK (vivid scene the viewer feels), CREATIVE ARCHETYPE, "
        "VISUAL DIRECTION (lighting, mood, props, people, environment), COMPOSITION (layout, camera angle, depth), "
        "COLOUR MOOD, brand accent usage, logo placement zone (clean top-left for logo overlay)\n"
        "- Describe a specific photorealistic scene tied to the keyword — e.g. SEO: analytics dashboard glow, "
        "PPC: ad performance review, social: content planning on phone, local SEO: map visibility moment\n"
        "- STRICT RULES block: NO text/words/logos/watermarks in image, NO stock clichés, photorealistic, "
        "square 1:1 friendly, unmistakably about the keyword service\n"
        "- Write like a senior creative director briefing a photographer — rich, cinematic, persuasive\n"
        "- post_angle = shorter copy direction for the text post (separate from image_prompt)\n"
        f"- return exactly {prompt_count} items, each visually distinct"
    )

    model = get_openrouter_prompt_model()
    try:
        content = await _call_openrouter_json(
            api_key=api_key,
            model=model,
            system=(
                "You are a senior Google Ads creative director producing high-converting display and "
                "GBP image briefs for Australian digital marketing agencies. Each image_prompt must be "
                "deep, detailed, persuasive, and unique. Respond with valid JSON only."
            ),
            user=user_prompt,
            temperature=0.9,
            max_tokens=6000,
        )
        parsed = _parse_openai_json_content(content)
    except json.JSONDecodeError as exc:
        logger.exception("Failed to parse OpenRouter prompt JSON")
        raise HTTPException(status_code=502, detail="OpenRouter returned invalid JSON for prompts.") from exc

    raw_items = parsed.get("prompts") if isinstance(parsed, dict) else None
    if not isinstance(raw_items, list):
        raw_items = []

    prompts_out: list[dict[str, str]] = []
    for i in range(prompt_count):
        item = raw_items[i] if i < len(raw_items) and isinstance(raw_items[i], dict) else {}
        keyword = re.sub(r"\s+", " ", str(item.get("keyword") or assigned_keywords[i]).strip())
        if not keyword:
            keyword = assigned_keywords[i]
        post_angle = re.sub(r"\s+", " ", str(item.get("post_angle") or "").strip())
        image_prompt = str(item.get("image_prompt") or "").strip()
        archetype = str(item.get("archetype") or "").strip().upper()

        if not image_prompt or len(image_prompt) < 120:
            from app.services.gbp_image_prompt_service import build_gbp_post_image_prompt

            image_prompt, _ = build_gbp_post_image_prompt(
                keyword=keyword,
                business_name=bname,
                metro=location_label,
                theme=post_angle or _GBP_DM_ANGLES[i % len(_GBP_DM_ANGLES)],
                post_body="",
                brand_config=brand,
                archetype=archetype if archetype in {
                    "SOCIAL_PROOF", "AUTHORITY", "URGENCY", "PROBLEM_SOLVE", "OFFER", "DATA_DRIVEN"
                } else "SOCIAL_PROOF",
                post_index=i + 1,
            )

        slot_parts = [image_prompt]
        if post_angle:
            slot_parts.append(f"\n---\nPost angle (for copy): {post_angle}")
        slot_parts.append(f"\nKEYWORD: {keyword}")
        slot = "".join(slot_parts)

        prompts_out.append({
            "direction": post_angle or image_prompt[:200],
            "keyword": keyword,
            "archetype": archetype,
            "image_prompt": image_prompt,
            "slot": slot,
        })

    return {
        "count": prompt_count,
        "prompts": prompts_out,
        "model": model,
        "keywords_selected": selected,
    }


async def generate_gbp_posts(
    session: AsyncSession,
    client_id: UUID,
    *,
    count: int = 1,
    prompts_raw: str | None = None,
) -> dict:
    settings = get_settings()
    if not (settings.anthropic_api_key or "").strip():
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY is not configured.")

    post_count = max(1, min(int(count), 10))
    profile = await _get_client_profile(session, client_id)
    brand = await get_brand_kit(session, client_id)
    location_ctx = await _build_location_context(session, client_id, profile)
    scope = str(location_ctx.get("scope") or "suburb")
    areas = await _areas_for_batch_posts(session, client_id, profile, post_count)
    primary = str(profile.get("primary_keyword") or "services").strip()
    city = str(location_ctx.get("city_name") or "")
    suburb_label = str(location_ctx.get("label") or "")

    ahrefs_kws = await _ahrefs_keywords_for_posts(session, client_id, profile, post_count)
    if not ahrefs_kws:
        if scope == "city" and city:
            ahrefs_kws = [f"{primary} {city}".strip(), f"{city} {primary}".strip()]
        elif suburb_label:
            ahrefs_kws = [f"{primary} {suburb_label}".strip(), f"{suburb_label} {primary}".strip()]
        else:
            ahrefs_kws = [primary]
        ahrefs_kws = [k for k in ahrefs_kws if k]

    user_prompt_slots = _parse_post_prompt_slots(prompts_raw, post_count)
    recent_hooks = await _recent_post_openings(session, client_id)

    if post_count == 1:
        await session.execute(
            text(
                """
                UPDATE rp_content_queue
                SET status = 'archived',
                    payload = COALESCE(payload, '{}'::jsonb) || '{"archived_reason": "superseded_by_new_draft"}'::jsonb,
                    updated_at = now()
                WHERE client_id = :cid AND content_type = 'gbp_post' AND status = 'pending'
                """
            ),
            {"cid": str(client_id)},
        )

    generated: list[dict] = []
    errors: list[str] = []
    keywords_used: list[str] = []
    batch_keywords_default = _pick_diverse_keywords(ahrefs_kws, post_count)
    resolved_keywords: list[str] = []
    resolved_directions: list[str | None] = []

    for i in range(post_count):
        slot = user_prompt_slots[i] if i < len(user_prompt_slots) else None
        target_kw, direction = _resolve_target_keyword_from_prompt(
            slot,
            ahrefs_kws,
            batch_keywords_default[i],
        )
        resolved_keywords.append(target_kw)
        resolved_directions.append(direction)

    prior_batch_summaries: list[str] = []
    prior_archetypes: list[str] = []

    user_prompts = _expand_directions_for_batch(
        resolved_directions,
        resolved_keywords,
        post_count,
        str(location_ctx.get("label") or suburb_label or city or "your area"),
    )

    for i in range(post_count):
        idx = i + 1
        target_kw = resolved_keywords[i]
        keywords_used.append(target_kw)
        direction = user_prompts[i] if i < len(user_prompts) else None
        try:
            item = await _generate_one_gbp_post(
                session,
                client_id,
                target_keyword=target_kw,
                area=areas[i],
                location_ctx=location_ctx,
                user_direction=direction,
                profile=profile,
                brand=brand,
                settings=settings,
                recent_hooks=recent_hooks,
                prior_batch_summaries=prior_batch_summaries,
                prior_archetypes=prior_archetypes,
                post_index=idx,
                post_total=post_count,
            )
            generated.append(item)
            summary = item.pop("batch_summary", None)
            if summary:
                prior_batch_summaries.append(summary)
            arch = item.pop("image_archetype", None)
            if arch:
                prior_archetypes.append(str(arch))
        except Exception as exc:
            logger.exception("GBP post %d/%d generation failed", idx, post_count)
            errors.append(f"Post {idx} ({target_kw}): {exc!s}")

    if not generated:
        raise HTTPException(
            status_code=502,
            detail=errors[0] if errors else "Failed to generate any posts.",
        )

    out: dict = {
        "generated": len(generated),
        "count": post_count,
        "keywords_used": keywords_used[: len(generated)],
        "posts": generated,
        "source": "ahrefs" if ahrefs_kws else "profile",
        "location_scope": scope,
        "target_area": str(location_ctx.get("area_full") or ""),
        "city_name": city,
    }
    if post_count == 1:
        out.update(generated[0])
        out["location_scope"] = scope
        out["target_area"] = str(location_ctx.get("area_full") or "")
        out["city_name"] = city
    if errors:
        out["warnings"] = errors
    return out


async def generate_weekly_post(
    session: AsyncSession,
    client_id: UUID,
    *,
    user_prompt: str | None = None,
    count: int = 1,
) -> dict:
    return await generate_gbp_posts(
        session,
        client_id,
        count=count,
        prompts_raw=user_prompt,
    )


async def _list_google_local_post_names(token: str, v4_parent: str) -> set[str]:
    """Names of local posts currently live on Google (accounts/.../locations/.../localPosts/...)."""
    names: set[str] = set()
    url = f"{GBP_V4_BASE}/{v4_parent}/localPosts"
    page_token: str | None = None
    async with httpx.AsyncClient(timeout=30.0) as http:
        headers = {"Authorization": f"Bearer {token}"}
        while True:
            params: dict[str, str | int] = {"pageSize": 100}
            if page_token:
                params["pageToken"] = page_token
            resp = await http.get(url, headers=headers, params=params)
            if not resp.is_success:
                msg = ""
                with contextlib.suppress(Exception):
                    msg = str(resp.json().get("error", {}).get("message") or "")
                logger.warning("GBP list localPosts failed: %s", msg or resp.text[:200])
                break
            data = resp.json() if isinstance(resp.json(), dict) else {}
            for item in data.get("localPosts") or []:
                if isinstance(item, dict):
                    name = str(item.get("name") or "").strip()
                    if name:
                        names.add(name)
            page_token = str(data.get("nextPageToken") or "").strip() or None
            if not page_token:
                break
    return names


async def sync_gbp_posts_with_google(session: AsyncSession, client_id: UUID) -> dict:
    """Mark queue posts as removed when deleted directly on Google Business Profile."""
    intg = await _gbp_integration(session, client_id)
    if not intg:
        return {"checked": 0, "removed": 0, "live_on_google": 0, "skipped": "not_connected"}

    from app.routes.v1.integrations import _get_google_access_token
    from app.services.gbp_photos_service import _resolve_v4_media_parent

    token = await _get_google_access_token(session, client_id, "gbp")
    v4_parent = await _resolve_v4_media_parent(token, intg["location_name"])
    live_names = await _list_google_local_post_names(token, v4_parent)

    rows = (
        await session.execute(
            text(
                """
                SELECT id, status, payload
                FROM rp_content_queue
                WHERE client_id = :cid
                  AND content_type = 'gbp_post'
                  AND status IN ('published', 'removed_on_gbp')
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().all()

    now = datetime.now(UTC)
    removed = 0
    restored = 0
    checked = 0
    for row in rows:
        payload = row["payload"] if isinstance(row["payload"], dict) else {}
        if isinstance(row["payload"], str):
            with contextlib.suppress(json.JSONDecodeError):
                payload = json.loads(row["payload"])
        gname = str(payload.get("gbp_local_post_name") or "").strip()
        if not gname:
            continue
        checked += 1
        on_google = gname in live_names
        cur = str(row["status"] or "")
        if not on_google and cur == "published":
            payload["removed_on_gbp_at"] = now.isoformat()
            await session.execute(
                text(
                    """
                    UPDATE rp_content_queue
                    SET status = 'removed_on_gbp',
                        payload = (CAST(:payload AS text))::jsonb,
                        updated_at = :now
                    WHERE id = :id AND client_id = :cid
                    """
                ),
                {
                    "id": str(row["id"]),
                    "cid": str(client_id),
                    "payload": json.dumps(payload),
                    "now": now,
                },
            )
            removed += 1
        elif on_google and cur == "removed_on_gbp":
            payload.pop("removed_on_gbp_at", None)
            await session.execute(
                text(
                    """
                    UPDATE rp_content_queue
                    SET status = 'published',
                        payload = (CAST(:payload AS text))::jsonb,
                        updated_at = :now
                    WHERE id = :id AND client_id = :cid
                    """
                ),
                {
                    "id": str(row["id"]),
                    "cid": str(client_id),
                    "payload": json.dumps(payload),
                    "now": now,
                },
            )
            restored += 1

    return {
        "checked": checked,
        "removed": removed,
        "restored": restored,
        "live_on_google": len(live_names),
    }


async def _publish_local_post_to_google(
    token: str,
    v4_parent: str,
    summary: str,
    media_source_url: str | None = None,
) -> str:
    from app.routes.v1.integrations import _gbp_google_error_detail

    body: dict[str, Any] = {
        "languageCode": "en-AU",
        "summary": normalize_gbp_post_body(summary),
        "topicType": "STANDARD",
    }
    if media_source_url:
        body["media"] = [{"mediaFormat": "PHOTO", "sourceUrl": media_source_url}]
    url = f"{GBP_V4_BASE}/{v4_parent}/localPosts"
    async with httpx.AsyncClient(timeout=60.0) as http:
        resp = await http.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
        )
    if not resp.is_success:
        msg = ""
        with contextlib.suppress(Exception):
            msg = str(resp.json().get("error", {}).get("message") or resp.json())
        detail = _gbp_google_error_detail(msg or resp.text[:300], context="GBP post publish failed")
        raise HTTPException(
            status_code=resp.status_code if resp.status_code < 500 else 502,
            detail=f"GBP is connected — Google rejected this post. {detail}",
        )
    data = resp.json() if isinstance(resp.json(), dict) else {}
    return str(data.get("name") or "")


async def publish_gbp_queue_post(
    session: AsyncSession,
    client_id: UUID,
    post_id: str,
    *,
    post_body_override: str | None = None,
    payload_override: dict | None = None,
) -> dict:
    """Push an approved GBP post (text + optional image) to Google."""
    payload = dict(payload_override or {})
    if not payload_override:
        row = (
            await session.execute(
                text(
                    """
                    SELECT id, status, payload
                    FROM rp_content_queue
                    WHERE id = :id AND client_id = :cid AND content_type = 'gbp_post'
                    """
                ),
                {"id": post_id, "cid": str(client_id)},
            )
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Post not found")

        payload = row["payload"] if isinstance(row["payload"], dict) else {}
        if isinstance(row["payload"], str):
            try:
                payload = json.loads(row["payload"])
            except json.JSONDecodeError:
                payload = {}

    post_body = normalize_gbp_post_body(str(post_body_override or payload.get("body") or "").strip())
    if not post_body:
        raise HTTPException(status_code=400, detail="Post body is empty")

    intg = await _gbp_integration(session, client_id)
    if not intg:
        raise HTTPException(
            status_code=400,
            detail=(
                "GBP is not fully set up. Connect Google Business Profile in onboarding, "
                "then select your listing (Select Property)."
            ),
        )

    from app.routes.v1.integrations import _get_google_access_token
    from app.services.gbp_photos_service import (
        _google_can_fetch_publish_url,
        _resolve_v4_media_parent,
        build_photo_publish_source_url,
    )

    settings = get_settings()
    token = await _get_google_access_token(session, client_id, "gbp")
    media_url = None
    photo_id = str(payload.get("photo_id") or "").strip()
    if photo_id and _google_can_fetch_publish_url(settings):
        media_url = build_photo_publish_source_url(photo_id, client_id, settings)
    note = (
        "Published to your Google Business Profile"
        + (" with image." if media_url else " (text only).")
    )
    if photo_id and not media_url:
        note = (
            "Published (text only). Image not sent — set PUBLIC_API_BASE_URL for Google to fetch photos."
        )

    v4_parent = await _resolve_v4_media_parent(token, intg["location_name"])
    try:
        gbp_post_name = await _publish_local_post_to_google(token, v4_parent, post_body, media_url)
    except HTTPException as exc:
        if media_url and exc.status_code in (400, 502):
            logger.warning("GBP post with image failed (%s), retrying text-only", exc.detail)
            gbp_post_name = await _publish_local_post_to_google(token, v4_parent, post_body, None)
            note = (
                "Published to Google (text only). Image was skipped — Google could not fetch the photo URL. "
                "Set PUBLIC_API_BASE_URL to a live https tunnel, or publish without the image."
            )
        else:
            raise
    was_removed = bool(payload.get("removed_on_gbp_at"))
    payload["body"] = post_body
    payload["word_count"] = len(post_body.split())
    payload["gbp_local_post_name"] = gbp_post_name
    payload.pop("removed_on_gbp_at", None)
    if was_removed:
        note = f"Republished to Google Business Profile. {note}"

    r = await session.execute(
        text(
            """
            UPDATE rp_content_queue
            SET status = 'published',
                payload = (CAST(:payload AS text))::jsonb,
                published_at = now(),
                updated_at = now()
            WHERE id = :id AND client_id = :cid AND content_type = 'gbp_post'
            RETURNING id, status
            """
        ),
        {"id": post_id, "cid": str(client_id), "payload": json.dumps(payload)},
    )
    updated = r.mappings().first()
    return {
        "id": str(updated["id"]),
        "status": updated["status"],
        "body": post_body,
        "note": note,
    }


GBP_DRIP_CADENCE_DAYS = 1


async def _next_drip_date(
    session: AsyncSession,
    client_id: UUID,
    *,
    content_type: str = "gbp_post",
    exclude_id: str | None = None,
    cadence_days: int = GBP_DRIP_CADENCE_DAYS,
) -> date:
    """Return the next free publish date so approved queue items drip out one per slot."""
    row = (
        await session.execute(
            text(
                """
                SELECT MAX((payload->>'scheduled_for')::date) AS last_date
                FROM rp_content_queue
                WHERE client_id = :cid
                  AND content_type = :ctype
                  AND status = 'approved'
                  AND COALESCE(payload->>'scheduled_for', '') <> ''
                  AND (:exclude IS NULL OR id <> :exclude)
                """
            ),
            {"cid": str(client_id), "ctype": content_type, "exclude": exclude_id},
        )
    ).mappings().first()

    today = datetime.now(UTC).date()
    last_date = row["last_date"] if row else None
    if last_date is None or last_date < today:
        return today
    return last_date + timedelta(days=max(1, cadence_days))


def _spread_dates(count: int, start: date, end: date) -> list[date]:
    """Evenly distribute `count` dates across the inclusive [start, end] range."""
    if count <= 0:
        return []
    if count == 1:
        return [start]
    if end <= start:
        return [start + timedelta(days=i) for i in range(count)]
    span = (end - start).days
    return [start + timedelta(days=round(i * span / (count - 1))) for i in range(count)]


async def schedule_all_pending_posts(
    session: AsyncSession,
    client_id: UUID,
    *,
    mode: str = "daily",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Approve/reschedule every unpublished GBP post and assign publish dates.

    Targets both pending and already-approved posts so the date range can be
    re-applied at any time.

    mode="daily": one post per day starting today (or start_date).
    mode="range": spread evenly between start_date and end_date.
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT id, payload
                FROM rp_content_queue
                WHERE client_id = :cid
                  AND content_type = 'gbp_post'
                  AND status IN ('pending', 'approved')
                ORDER BY
                  COALESCE(payload->>'scheduled_for', '9999-12-31') ASC,
                  created_at ASC
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().all()

    if not rows:
        raise HTTPException(status_code=400, detail="No posts available to schedule.")

    today = datetime.now(UTC).date()

    def _parse(d: str | None, fallback: date) -> date:
        if not (d or "").strip():
            return fallback
        try:
            return date.fromisoformat(d.strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    start = _parse(start_date, today)
    if start < today:
        start = today

    count = len(rows)
    if mode == "range":
        end = _parse(end_date, start + timedelta(days=max(0, count - 1)))
        if end < start:
            end = start
        dates = _spread_dates(count, start, end)
    else:  # daily
        dates = [start + timedelta(days=i) for i in range(count)]

    scheduled: list[dict] = []
    for r, d in zip(rows, dates, strict=False):
        payload = r["payload"] if isinstance(r["payload"], dict) else {}
        if isinstance(r["payload"], str):
            try:
                payload = json.loads(r["payload"])
            except json.JSONDecodeError:
                payload = {}
        if not str(payload.get("body") or "").strip():
            continue
        payload["scheduled_for"] = d.isoformat()
        await session.execute(
            text(
                """
                UPDATE rp_content_queue
                SET status = 'approved',
                    payload = (CAST(:payload AS text))::jsonb,
                    updated_at = now()
                WHERE id = :id AND client_id = :cid AND content_type = 'gbp_post'
                """
            ),
            {"id": str(r["id"]), "cid": str(client_id), "payload": json.dumps(payload)},
        )
        scheduled.append({"id": str(r["id"]), "scheduled_for": d.isoformat()})

    return {
        "approved": len(scheduled),
        "mode": mode,
        "first_date": scheduled[0]["scheduled_for"] if scheduled else None,
        "last_date": scheduled[-1]["scheduled_for"] if scheduled else None,
        "posts": scheduled,
    }


async def update_gbp_post(
    session: AsyncSession,
    client_id: UUID,
    post_id: str,
    *,
    status: str | None = None,
    body: str | None = None,
    scheduled_for: str | None = None,
) -> dict:
    if status is None and body is None and scheduled_for is None:
        raise HTTPException(status_code=400, detail="Provide body, status, and/or scheduled_for to update")
    if status is not None and status not in ("approved", "rejected", "published", "removed_on_gbp"):
        raise HTTPException(status_code=400, detail="Invalid status")

    # Validate an explicit publish date if the user picked one.
    chosen_date: str | None = None
    if scheduled_for is not None and scheduled_for.strip():
        try:
            chosen_date = date.fromisoformat(scheduled_for.strip()).isoformat()
        except ValueError:
            raise HTTPException(status_code=400, detail="scheduled_for must be YYYY-MM-DD")

    row = (
        await session.execute(
            text(
                """
                SELECT id, status, payload
                FROM rp_content_queue
                WHERE id = :id AND client_id = :cid AND content_type = 'gbp_post'
                """
            ),
            {"id": post_id, "cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")

    payload = row["payload"] if isinstance(row["payload"], dict) else {}
    if isinstance(row["payload"], str):
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            payload = {}
    if body is not None:
        edited = body.strip()
        if not edited:
            raise HTTPException(status_code=400, detail="Post text cannot be empty")
        payload["body"] = edited
        payload["word_count"] = len(edited.split())

    # A user-chosen publish date always wins over the auto drip date.
    if chosen_date is not None:
        payload["scheduled_for"] = chosen_date

    post_body = str(payload.get("body") or "").strip()
    note = "Draft saved."
    final_status = str(row.get("status") or "pending")

    if status is None:
        await session.execute(
            text(
                """
                UPDATE rp_content_queue
                SET payload = (CAST(:payload AS text))::jsonb, updated_at = now()
                WHERE id = :id AND client_id = :cid AND content_type = 'gbp_post'
                RETURNING id, status
                """
            ),
            {"id": post_id, "cid": str(client_id), "payload": json.dumps(payload)},
        )
        return {"id": post_id, "status": final_status, "body": post_body, "note": note}

    if not post_body and status in ("approved", "published"):
        raise HTTPException(status_code=400, detail="Post body is empty")

    if status == "published":
        await session.execute(
            text(
                """
                UPDATE rp_content_queue
                SET payload = (CAST(:payload AS text))::jsonb, updated_at = now()
                WHERE id = :id AND client_id = :cid AND content_type = 'gbp_post'
                """
            ),
            {"id": post_id, "cid": str(client_id), "payload": json.dumps(payload)},
        )
        return await publish_gbp_queue_post(
            session,
            client_id,
            post_id,
            post_body_override=post_body,
            payload_override=payload,
        )

    final_status = status
    if status == "approved":
        scheduled = str(payload.get("scheduled_for") or "").strip()
        if not scheduled:
            # Auto-assign the next drip slot so the scheduler publishes it automatically.
            drip = await _next_drip_date(session, client_id, exclude_id=post_id)
            scheduled = drip.isoformat()
            payload["scheduled_for"] = scheduled
        today_str = datetime.now(UTC).date().isoformat()
        if scheduled <= today_str:
            note = f"Approved — auto-publishing today ({scheduled}) on the next scheduled run."
        else:
            note = f"Approved — scheduled to auto-publish on {scheduled}."
    elif status == "rejected":
        note = "Post rejected."
    elif status == "removed_on_gbp":
        note = "Marked as removed on Google Business Profile."
        payload["removed_on_gbp_at"] = datetime.now(UTC).isoformat()

    r = await session.execute(
        text(
            """
            UPDATE rp_content_queue
            SET status = :st,
                payload = (CAST(:payload AS text))::jsonb,
                published_at = CASE WHEN :st = 'published' THEN now() ELSE published_at END,
                updated_at = now()
            WHERE id = :id AND client_id = :cid AND content_type = 'gbp_post'
            RETURNING id, status
            """
        ),
        {
            "st": final_status,
            "id": post_id,
            "cid": str(client_id),
            "payload": json.dumps(payload),
        },
    )
    updated = r.mappings().first()
    return {
        "id": str(updated["id"]),
        "status": updated["status"],
        "body": post_body,
        "note": note,
    }


async def delete_gbp_post(session: AsyncSession, client_id: UUID, post_id: str) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT id, status, payload
                FROM rp_content_queue
                WHERE id = :id AND client_id = :cid AND content_type = 'gbp_post'
                """
            ),
            {"id": post_id, "cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")

    payload = row["payload"] if isinstance(row["payload"], dict) else {}
    if isinstance(row["payload"], str):
        with contextlib.suppress(json.JSONDecodeError):
            payload = json.loads(row["payload"])

    status = str(row.get("status") or "")
    if status == "published":
        payload["archived_reason"] = "user_removed_from_history"
        await session.execute(
            text(
                """
                UPDATE rp_content_queue
                SET status = 'archived',
                    payload = (CAST(:payload AS text))::jsonb,
                    updated_at = now()
                WHERE id = :id AND client_id = :cid AND content_type = 'gbp_post'
                """
            ),
            {"id": post_id, "cid": str(client_id), "payload": json.dumps(payload)},
        )
        return {"deleted": post_id, "mode": "archived"}

    photo_id = str(payload.get("photo_id") or "").strip()
    if photo_id:
        from app.services.gbp_photos_service import delete_gbp_photo

        with contextlib.suppress(Exception):
            await delete_gbp_photo(session, client_id, photo_id)

    await session.execute(
        text(
            """
            DELETE FROM rp_content_queue
            WHERE id = :id AND client_id = :cid AND content_type = 'gbp_post'
            """
        ),
        {"id": post_id, "cid": str(client_id)},
    )
    return {"deleted": post_id, "mode": "deleted"}


def _gbp_post_ends_complete(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return t[-1] in ".!?)]\"'"


def _trim_gbp_post_to_limit(text: str, limit: int = GBP_POST_CHAR_LIMIT) -> str:
    """Trim to Google's post limit without cutting mid-word."""
    body = (text or "").strip()
    if len(body) <= limit:
        return body
    chunk = body[:limit]
    for sep in (". ", "! ", "? ", ".\n", "!\n", "?\n"):
        idx = chunk.rfind(sep)
        if idx >= int(limit * 0.55):
            return chunk[: idx + len(sep.rstrip())].strip()
    sp = chunk.rfind(" ")
    if sp > 0:
        return chunk[:sp].strip()
    return chunk.strip()


def normalize_gbp_post_body(text: str, *, api_key: str | None = None) -> str:
    """Ensure GBP post fits 1,500 chars and ends on a complete sentence."""
    body = _trim_gbp_post_to_limit(text)
    if _gbp_post_ends_complete(body):
        return body
    if api_key:
        try:
            completed = _call_claude(
                "Finish this Google Business Profile post: complete the cut-off last sentence "
                f"and add a short call-to-action. Return the FULL post text only (max {GBP_POST_CHAR_LIMIT} "
                "characters). Do not start over from scratch.\n\n"
                f"{body}",
                api_key,
                max_tokens=2048,
            )
            body = _trim_gbp_post_to_limit(completed.strip())
            if _gbp_post_ends_complete(body):
                return body
        except Exception:
            logger.warning("GBP post auto-completion skipped", exc_info=True)
    for sep in (". ", "! ", "? "):
        idx = body.rfind(sep)
        if idx > 0:
            return body[: idx + 1].strip()
    return body


def _truncate_gbp_description(text: str, limit: int = 750) -> str:
    """Return text trimmed to `limit` chars, always ending at a complete sentence."""
    body = (text or "").strip()
    if len(body) <= limit:
        return body
    window = body[:limit]
    # Try last sentence-ending punctuation in the second half of the window
    for punct in (".", "!", "?"):
        last = window.rfind(punct)
        if last > limit // 2:
            return window[: last + 1].strip()
    # Fall back to last word boundary
    last_space = window.rfind(" ")
    if last_space > limit // 2:
        return window[:last_space].strip()
    return window.strip()


async def _publish_description_to_google(token: str, location_name: str, description: str) -> None:
    from app.routes.v1.integrations import _gbp_google_error_detail

    body = _truncate_gbp_description(description)
    qs = "updateMask=profile.description"
    url = f"{BI_BASE}/{location_name}?{qs}"
    async with httpx.AsyncClient(timeout=25) as http:
        resp = await http.patch(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"profile": {"description": body}},
        )
    if not resp.is_success:
        msg = ""
        with contextlib.suppress(Exception):
            msg = str(resp.json().get("error", {}).get("message") or "")
        raise HTTPException(
            status_code=resp.status_code,
            detail=_gbp_google_error_detail(msg, context="GBP description update failed"),
        )


def _ensure_keywords_in_description(body: str, keywords: list[str], limit: int = 750) -> str:
    """Ensure up to two target phrases appear once — no keyword stuffing."""
    text = (body or "").strip()
    targets = [
        re.sub(r"\s+", " ", (kw or "").strip())
        for kw in (keywords or [])[:2]
        if len((kw or "").strip()) >= 3
    ]
    if not text or not targets:
        return _truncate_gbp_description(text, limit)

    low = text.lower()
    missing = [kw for kw in targets if kw.lower() not in low]
    if not missing:
        return _truncate_gbp_description(text, limit)

    if len(missing) == 1:
        suffix = f" Ask us about {missing[0]}."
    else:
        suffix = f" We help with {missing[0]} and {missing[1]}."
    if len(text) + len(suffix) <= limit:
        text = text.rstrip(".") + "." + suffix if not text.endswith(".") else text + suffix
    return _truncate_gbp_description(text, limit)


async def publish_gbp_queue_description(
    session: AsyncSession,
    client_id: UUID,
    desc_id: str,
    *,
    body_override: str | None = None,
) -> dict:
    """Push an approved GBP business description to Google."""
    row = (
        await session.execute(
            text(
                """
                SELECT id, status, payload
                FROM rp_content_queue
                WHERE id = :id AND client_id = :cid AND content_type = 'gbp_description'
                """
            ),
            {"id": desc_id, "cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Description not found")

    payload = row["payload"] if isinstance(row["payload"], dict) else {}
    if isinstance(row["payload"], str):
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            payload = {}

    desc_body = _truncate_gbp_description(str(body_override or payload.get("body") or "").strip())
    if not desc_body:
        raise HTTPException(status_code=400, detail="Description body is empty")

    intg = await _gbp_integration(session, client_id)
    if not intg:
        raise HTTPException(
            status_code=400,
            detail=(
                "GBP is not fully set up. Connect Google Business Profile in onboarding, "
                "then select your listing (Select Property)."
            ),
        )

    from app.routes.v1.integrations import _get_google_access_token

    token = await _get_google_access_token(session, client_id, "gbp")
    await _publish_description_to_google(token, intg["location_name"], desc_body)

    payload["body"] = desc_body
    payload["char_count"] = len(desc_body)
    r = await session.execute(
        text(
            """
            UPDATE rp_content_queue
            SET status = 'published',
                payload = (CAST(:payload AS text))::jsonb,
                published_at = now(),
                updated_at = now()
            WHERE id = :id AND client_id = :cid AND content_type = 'gbp_description'
            RETURNING id, status
            """
        ),
        {"id": desc_id, "cid": str(client_id), "payload": json.dumps(payload)},
    )
    updated = r.mappings().first()
    return {
        "id": str(updated["id"]),
        "status": updated["status"],
        "body": desc_body,
        "char_count": len(desc_body),
        "note": "Published to your Google Business Profile.",
    }


async def generate_gbp_description(
    session: AsyncSession,
    client_id: UUID,
    *,
    user_keywords: list[str] | None = None,
) -> dict:
    from app.core.config import get_openrouter_api_key, get_openrouter_prompt_model

    api_key = get_openrouter_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY is not configured.")

    intg = await _gbp_integration(session, client_id)
    if not intg:
        raise HTTPException(status_code=400, detail="Connect GBP and select a location first.")

    profile = await _get_client_profile(session, client_id)
    metro = str(profile.get("metro_label") or "").strip()
    scope = str(profile.get("location_scope") or "suburb").strip().lower()
    city = _metro_city_name(metro)
    keyword = str(profile.get("primary_keyword") or "services").strip()
    primaries = parse_primary_keywords(keyword) or [keyword]
    bname = str(profile.get("business_name") or "Your business").strip()
    brand = await get_brand_kit(session, client_id)
    brand_voice = str(brand.get("brand_voice") or "").strip()

    if scope == "city":
        area_list = city or metro or "your city"
        suburb_entries: list[str] = []
    else:
        suburb_entries = await _get_top_suburbs(session, client_id, 3)
        area_list = ", ".join(suburb_entries) if suburb_entries else (city or metro or "your area")

    user_picked = [
        re.sub(r"\s+", " ", k.strip())
        for k in (user_keywords or [])
        if (k or "").strip()
    ][:2]

    if not user_picked:
        raise HTTPException(
            status_code=400,
            detail="Select 1–2 keywords on the left before generating a description.",
        )

    combined = list(dict.fromkeys(user_picked))
    keyword_lines = "\n".join(f"- {kw}" for kw in combined)
    area_label = "City" if scope == "city" else "Service areas"
    services_line = ", ".join(primaries[:3])

    user_prompt = (
        f"Write a Google Business Profile business description for:\n\n"
        f"Business: {bname}\n"
        f"Core services: {services_line}\n"
        f"{area_label}: {area_list}\n"
        f"Brand voice: {brand_voice or 'professional, trustworthy, local expert'}\n\n"
        f"TARGET KEYWORDS — use ONLY these exact phrases (each at most ONCE):\n"
        f"{keyword_lines}\n\n"
        f"STRICT requirements:\n"
        f"- Total length: 700–750 CHARACTERS (Google limit — count characters, not words)\n"
        f"- Use each target keyword exactly once, woven into natural sentences\n"
        f"- Do NOT repeat keywords or create close variations (no stuffing)\n"
        f"- Do NOT list keywords back-to-back or force every service phrase into one paragraph\n"
        f"- Write like a real business owner: who you are, what you do, who you help, where you serve\n"
        f"- End with one complete sentence and a short call-to-action\n"
        f"- Plain text only — no markdown, no bullet points, no line breaks\n"
        f"- Every sentence must add value — no filler\n"
    )

    model = get_openrouter_prompt_model()
    try:
        raw = await _call_openrouter_text(
            api_key=api_key,
            model=model,
            system=(
                "You write natural, human-sounding Google Business Profile descriptions for Australian "
                "service businesses. Use each provided keyword phrase once only — never keyword-stuff "
                "or repeat similar phrases. Output plain text only — no quotes, no labels, no markdown. "
                "Stay within 750 characters."
            ),
            user=user_prompt,
            temperature=0.85,
            max_tokens=900,
        )
        body = _ensure_keywords_in_description(raw, combined)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("GBP description generation failed")
        raise HTTPException(status_code=502, detail=f"Failed to generate description: {exc}") from exc

    now = datetime.now(UTC)
    desc_id = str(uuid7())
    title = f"GBP Description — {bname}"
    await session.execute(
        text(
            """
            DELETE FROM rp_content_queue
            WHERE client_id = :cid AND content_type = 'gbp_description' AND status = 'pending'
            """
        ),
        {"cid": str(client_id)},
    )
    await session.execute(
        text(
            """
            INSERT INTO rp_content_queue
                (id, client_id, content_type, status, approval_mode,
                 payload, generated_at, created_at, updated_at)
            VALUES
                (:id, :cid, 'gbp_description', 'pending', 'approval_required',
                 (CAST(:payload AS text))::jsonb, :now, :now, :now)
            """
        ),
        {
            "id": desc_id,
            "cid": str(client_id),
            "now": now,
            "payload": json.dumps({
                "title": title,
                "body": body,
                "char_count": len(body),
                "keywords_used": combined,
                "model": model,
                "notes": "Google Business Profile description (≤750 chars)",
            }),
        },
    )
    return {
        "id": desc_id,
        "title": title,
        "body": body,
        "status": "pending",
        "char_count": len(body),
        "keywords_used": combined,
        "model": model,
    }


async def update_gbp_description(
    session: AsyncSession,
    client_id: UUID,
    desc_id: str,
    *,
    status: str | None = None,
    body: str | None = None,
    scheduled_for: str | None = None,
) -> dict:
    if status is None and body is None and scheduled_for is None:
        raise HTTPException(status_code=400, detail="Provide body, status, and/or scheduled_for to update")
    if status is not None and status not in ("approved", "rejected", "published"):
        raise HTTPException(status_code=400, detail="Invalid status")

    chosen_date: str | None = None
    if scheduled_for is not None and scheduled_for.strip():
        try:
            chosen_date = date.fromisoformat(scheduled_for.strip()).isoformat()
        except ValueError:
            raise HTTPException(status_code=400, detail="scheduled_for must be YYYY-MM-DD")

    row = (
        await session.execute(
            text(
                """
                SELECT id, status, payload
                FROM rp_content_queue
                WHERE id = :id AND client_id = :cid AND content_type = 'gbp_description'
                """
            ),
            {"id": desc_id, "cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Description not found")

    payload = row["payload"] if isinstance(row["payload"], dict) else {}
    if isinstance(row["payload"], str):
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            payload = {}

    if body is not None:
        edited = _truncate_gbp_description(body.strip())
        if not edited:
            raise HTTPException(status_code=400, detail="Description cannot be empty")
        payload["body"] = edited
        payload["char_count"] = len(edited)

    if chosen_date is not None:
        payload["scheduled_for"] = chosen_date

    desc_body = str(payload.get("body") or "").strip()
    note = "Draft saved."
    final_status = str(row.get("status") or "pending")

    if status is None:
        await session.execute(
            text(
                """
                UPDATE rp_content_queue
                SET payload = (CAST(:payload AS text))::jsonb, updated_at = now()
                WHERE id = :id AND client_id = :cid AND content_type = 'gbp_description'
                RETURNING id, status
                """
            ),
            {"id": desc_id, "cid": str(client_id), "payload": json.dumps(payload)},
        )
        return {
            "id": desc_id,
            "status": final_status,
            "body": desc_body,
            "char_count": len(desc_body),
            "scheduled_for": payload.get("scheduled_for"),
            "note": note,
        }

    if not desc_body and status in ("approved", "published"):
        raise HTTPException(status_code=400, detail="Description body is empty")

    if status == "published":
        await session.execute(
            text(
                """
                UPDATE rp_content_queue
                SET payload = (CAST(:payload AS text))::jsonb, updated_at = now()
                WHERE id = :id AND client_id = :cid AND content_type = 'gbp_description'
                """
            ),
            {"id": desc_id, "cid": str(client_id), "payload": json.dumps(payload)},
        )
        return await publish_gbp_queue_description(session, client_id, desc_id, body_override=desc_body)

    final_status = status
    if status == "approved":
        scheduled = str(payload.get("scheduled_for") or "").strip()
        if not scheduled:
            drip = await _next_drip_date(
                session, client_id, content_type="gbp_description", exclude_id=desc_id
            )
            scheduled = drip.isoformat()
            payload["scheduled_for"] = scheduled
        today_str = datetime.now(UTC).date().isoformat()
        if scheduled <= today_str:
            note = f"Approved — auto-publishes to GBP on {scheduled} (next scheduler run)."
        else:
            note = f"Approved — scheduled to publish to GBP on {scheduled}."
    elif status == "rejected":
        note = "Description rejected."

    r = await session.execute(
        text(
            """
            UPDATE rp_content_queue
            SET status = :st,
                payload = (CAST(:payload AS text))::jsonb,
                updated_at = now()
            WHERE id = :id AND client_id = :cid AND content_type = 'gbp_description'
            RETURNING id, status
            """
        ),
        {"st": final_status, "id": desc_id, "cid": str(client_id), "payload": json.dumps(payload)},
    )
    updated = r.mappings().first()
    return {
        "id": str(updated["id"]),
        "status": updated["status"],
        "body": desc_body,
        "char_count": len(desc_body),
        "scheduled_for": payload.get("scheduled_for"),
        "note": note,
    }


async def save_description_draft(session: AsyncSession, client_id: UUID, body: str) -> dict:
    """Create or update the pending GBP description draft (manual edits)."""
    edited = _truncate_gbp_description(body.strip())
    if not edited:
        raise HTTPException(status_code=400, detail="Description cannot be empty")

    existing = (
        await session.execute(
            text(
                """
                SELECT id FROM rp_content_queue
                WHERE client_id = :cid AND content_type = 'gbp_description' AND status = 'pending'
                LIMIT 1
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().first()

    if existing:
        return await update_gbp_description(
            session, client_id, str(existing["id"]), body=edited
        )

    profile = await _get_client_profile(session, client_id)
    title = f"GBP Description — {profile.get('business_name') or 'Business'}"
    desc_id = str(uuid7())
    now = datetime.now(UTC)
    payload = {
        "title": title,
        "body": edited,
        "char_count": len(edited),
        "notes": "Google Business Profile description (≤750 chars)",
    }
    await session.execute(
        text(
            """
            INSERT INTO rp_content_queue
                (id, client_id, content_type, status, approval_mode,
                 payload, generated_at, created_at, updated_at)
            VALUES
                (:id, :cid, 'gbp_description', 'pending', 'approval_required',
                 (CAST(:payload AS text))::jsonb, :now, :now, :now)
            """
        ),
        {
            "id": desc_id,
            "cid": str(client_id),
            "now": now,
            "payload": json.dumps(payload),
        },
    )
    return {
        "id": desc_id,
        "title": title,
        "body": edited,
        "status": "pending",
        "char_count": len(edited),
        "note": "Draft saved.",
    }


async def update_description_status(
    session: AsyncSession, client_id: UUID, desc_id: str, new_status: str
) -> dict:
    return await update_gbp_description(session, client_id, desc_id, status=new_status)
