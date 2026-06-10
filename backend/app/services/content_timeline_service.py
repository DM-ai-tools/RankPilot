"""One-month content calendar — weekly GBP posts + landing pages from Ahrefs keywords."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.core.config import get_settings
from app.services.content_generation_service import _business_from_url, _call_claude, _claude_model, _get_client_profile
from app.services.gbp_service import GBP_POST_CHAR_LIMIT, normalize_gbp_post_body
from app.services.gbp_brand_kit_service import get_brand_kit
from app.services.keyword_research_service import fetch_suburb_keyword_research

logger = logging.getLogger(__name__)

WEEKS = 4


async def generate_monthly_timeline(session: AsyncSession, client_id: UUID) -> dict:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return {"error": "ANTHROPIC_API_KEY is not set in backend/.env"}

    profile = await _get_client_profile(session, client_id)
    if not profile.get("business_name"):
        return {"error": "Complete onboarding first."}

    try:
        research = await fetch_suburb_keyword_research(
            session, client_id, suburb_limit=8, idea_limit=25, force_refresh=False
        )
    except Exception as exc:
        logger.exception("Ahrefs research for timeline failed")
        return {"error": f"Could not load Ahrefs keywords: {exc}"}

    from app.schemas.keywords import SuburbKeywordPhrase

    phrases = list(research.suburb_phrases or [])
    phrases.sort(key=lambda p: int(p.opportunity_score or 0), reverse=True)
    if not phrases:
        phrases = [
            SuburbKeywordPhrase(
                keyword=i.keyword,
                suburb=i.suburb or "",
                state=None,
                avg_monthly_searches=i.avg_monthly_searches,
                competition=i.competition,
                difficulty=i.difficulty,
                opportunity_score=i.opportunity_score or 0,
                traffic_potential=i.traffic_potential,
            )
            for i in (research.related_ideas or [])[:WEEKS]
        ]

    if not phrases:
        return {"error": "No Ahrefs keywords found — run onboarding and ensure AHREFS_API_KEY is set."}

    scope = str(research.location_scope or "suburb").strip().lower()
    area_label = "City" if scope == "city" else "Suburb"

    bname = str(profile.get("business_name") or "").strip()
    burl = str(profile.get("business_url") or "").strip()
    url_brand = _business_from_url(burl)
    prompt_business = url_brand or bname
    keyword = str(profile.get("primary_keyword") or prompt_business).strip()
    metro = str(profile.get("metro_label") or "").strip()
    brand = await get_brand_kit(session, client_id)
    brand_voice = str(brand.get("brand_voice") or "").strip()

    await session.execute(
        text(
            """
            DELETE FROM rp_content_queue
            WHERE client_id = :cid
              AND status = 'pending'
              AND content_type IN ('gbp_post', 'landing_page')
              AND COALESCE(payload->>'timeline_batch', '') = 'monthly'
            """
        ),
        {"cid": str(client_id)},
    )

    now = datetime.now(UTC)
    generated: list[dict] = []
    errors: list[str] = []
    prior_archetypes: list[str] = []

    for week in range(1, WEEKS + 1):
        row = phrases[(week - 1) % len(phrases)]
        area = str(row.suburb or metro.split(",")[0] or "your area").strip()
        target_kw = str(row.keyword or f"{keyword} {area}").strip()
        scheduled = (now + timedelta(days=7 * (week - 1))).date().isoformat()
        location_line = f"{area}, {metro}" if metro else area

        post_prompt = (
            f"Write a Google Business Profile post (160–200 words, max {GBP_POST_CHAR_LIMIT} characters) for:\n\n"
            f"Business: {prompt_business}\n"
            f"Target keyword (Ahrefs): {target_kw}\n"
            f"{area_label} focus: {area}\n"
            f"Metro: {metro}\n"
            f"Week {week} of a 4-week content calendar.\n"
            f"{f'Brand voice: {brand_voice}' if brand_voice else ''}\n\n"
            f"Use the keyword naturally. Include 3 bullet tips and a complete CTA sentence. "
            f"Plain text, emoji ok. Never stop mid-word."
        )
        try:
            post_body = normalize_gbp_post_body(
                _call_claude(post_prompt, settings.anthropic_api_key, max_tokens=4096).strip(),
                api_key=settings.anthropic_api_key,
            )
        except Exception as exc:
            errors.append(f"Week {week} GBP post: {exc!s}")
            post_body = ""

        photo_id = None
        photo_url = None
        image_note = ""
        if post_body:
            from app.services.gbp_photos_service import generate_post_image_from_content

            img = await generate_post_image_from_content(
                session,
                client_id,
                post_body,
                business_name=prompt_business,
                keyword=target_kw,
                metro=metro or area,
                theme=f"Week {week}: {target_kw}",
                brand_config=brand,
                post_index=week,
                post_total=WEEKS,
                prior_archetypes=prior_archetypes,
            )
            if img:
                photo_id = img.get("photo_id")
                photo_url = img.get("url")
                image_note = f"AI image generated (Runway, {img.get('archetype', 'creative')} style)."
                if img.get("archetype"):
                    prior_archetypes.append(str(img["archetype"]))
            elif not (settings.runwayml_api_key or "").strip():
                image_note = "No image — set RUNWAYML_API_KEY for post photos."

        if post_body:
            post_id = str(uuid7())
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
                        "title": f"Week {week} GBP post — {target_kw}",
                        "body": post_body,
                        "word_count": len(post_body.split()),
                        "notes": f"Scheduled for {scheduled} · Ahrefs keyword",
                        "target_keyword": target_kw,
                        "suburb": area,
                        "location_scope": scope,
                        "week_number": week,
                        "scheduled_for": scheduled,
                        "timeline_batch": "monthly",
                        "keyword_volume": row.avg_monthly_searches,
                        "keyword_difficulty": row.difficulty,
                        "photo_id": photo_id,
                        "photo_url": photo_url,
                        "image_note": image_note,
                    }),
                },
            )
            generated.append({
                "week": week,
                "type": "gbp_post",
                "keyword": target_kw,
                "scheduled_for": scheduled,
                "has_image": bool(photo_id),
            })

        page_prompt = (
            f"You are an SEO copywriter for an Australian local business.\n\n"
            f"Business: {prompt_business}\n"
            f"Target keyword (Ahrefs): {target_kw}\n"
            f"Location: {location_line}\n"
            f"Website: {burl}\n"
            f"Week {week} landing page in a 4-week plan.\n\n"
            f"Write ~400 words: H1, 2–3 paragraphs, 4–5 service bullets, CTA. "
            f"Return ONLY body text (no HTML)."
        )
        try:
            page_body = _call_claude(page_prompt, settings.anthropic_api_key).strip()
        except Exception as exc:
            errors.append(f"Week {week} landing page: {exc!s}")
            page_body = ""

        if page_body:
            area_slug = area.replace(", ", "-").replace(" ", "-").lower()
            page_id = str(uuid7())
            await session.execute(
                text(
                    """
                    INSERT INTO rp_content_queue
                        (id, client_id, content_type, status, approval_mode,
                         payload, generated_at, created_at, updated_at)
                    VALUES
                        (:id, :cid, 'landing_page', 'pending', 'approval_required',
                         (CAST(:payload AS text))::jsonb, :now, :now, :now)
                    """
                ),
                {
                    "id": page_id,
                    "cid": str(client_id),
                    "now": now,
                    "payload": json.dumps({
                        "title": f"{target_kw} — Landing Page (Week {week})",
                        "body": page_body,
                        "word_count": len(page_body.split()),
                        "notes": f"Scheduled for {scheduled} · Ahrefs-driven",
                        "target_keyword": target_kw,
                        "suburb": area,
                        "location_scope": scope,
                        "week_number": week,
                        "scheduled_for": scheduled,
                        "timeline_batch": "monthly",
                        "target_url": f"{burl}/{area_slug}/" if burl else "",
                    }),
                },
            )
            generated.append({"week": week, "type": "landing_page", "keyword": target_kw, "scheduled_for": scheduled})

    await session.commit()
    out: dict = {
        "generated": len(generated),
        "weeks": WEEKS,
        "items": generated,
        "model": _claude_model(),
        "source": research.source,
    }
    if errors:
        out["warnings"] = errors
    if not generated:
        out["error"] = errors[0] if errors else "No timeline items were created."
    return out
