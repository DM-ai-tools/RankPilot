"""GBP / Google Ads-style image prompts for Runway — unique, keyword-matched creatives."""

from __future__ import annotations

import json
import random
import re
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

BackgroundKind = Literal["light", "dark"]

# Expected scene brightness — drives logo variant (black on light, white on dark).
_ARCHETYPE_BACKGROUND: dict[str, BackgroundKind] = {
    "SOCIAL_PROOF": "light",
    "OFFER": "light",
    "AUTHORITY": "dark",
    "DATA_DRIVEN": "dark",
    "URGENCY": "light",
    "PROBLEM_SOLVE": "light",
}


def backdrop_for_archetype(archetype: str) -> BackgroundKind:
    return _ARCHETYPE_BACKGROUND.get(archetype, "light")

# ── Archetypes (from google_ads_backend_prompt_skeleton.md) ─────────────────

AD_ARCHETYPES: dict[str, dict[str, Any]] = {
    "SOCIAL_PROOF": {
        "visual_direction": (
            "Clean bright workspace or client success scene. Warm, trustworthy, approachable. "
            "Subtle star-rating or results vibe through environment (happy team, dashboard glow), "
            "not literal UI chrome."
        ),
        "colour_mood": "Light, trustworthy, professional",
        "visual_elements": ["warm natural light", "team collaboration", "subtle success cues"],
        "best_for": "commercial",
    },
    "AUTHORITY": {
        "visual_direction": (
            "Premium dark navy or charcoal setting with a single gold or white accent. "
            "Established, institutional, expert — minimal clutter, high-end agency feel."
        ),
        "colour_mood": "Dark, premium, trustworthy",
        "visual_elements": ["premium dark backdrop", "single accent colour", "confident expert mood"],
        "best_for": "commercial",
    },
    "URGENCY": {
        "visual_direction": (
            "Energetic brand-colour dominant scene with movement and action. "
            "Time-sensitive campaign energy — dynamic angle, warm highlights, decisive mood."
        ),
        "colour_mood": "Energetic, warm, action-oriented",
        "visual_elements": ["bold colour field", "dynamic composition", "high energy lighting"],
        "best_for": "transactional",
    },
    "PROBLEM_SOLVE": {
        "visual_direction": (
            "Split or contrasting scene: tension on one side, relief/solution on the other. "
            "Empathetic, direct — shows transformation from problem to clarity."
        ),
        "colour_mood": "Contrasting, empathetic, direct",
        "visual_elements": ["before/after contrast", "relief lighting", "focused subject"],
        "best_for": "informational",
    },
    "OFFER": {
        "visual_direction": (
            "Clean white or very light scene. Offer/value is the hero through clear service delivery "
            "imagery — consultation, audit, handshake, checklist — transactional and no-nonsense."
        ),
        "colour_mood": "Clean, clear, transactional",
        "visual_elements": ["bright clean background", "service delivery moment", "green accent hints"],
        "best_for": "transactional",
    },
    "DATA_DRIVEN": {
        "visual_direction": (
            "Dark tech-style scene with blue or cyan accent. Subtle grid or analytics atmosphere "
            "— performance-focused, modern, analytical (no cheesy clip-art charts)."
        ),
        "colour_mood": "Dark, techy, analytical",
        "visual_elements": ["dark tech backdrop", "subtle grid lines", "performance mood"],
        "best_for": "informational",
    },
}

LAYOUT_VARIANTS = [
    "subject left third with negative space on the right",
    "centred hero subject with soft depth-of-field background",
    "top-heavy composition with subject in upper two-thirds",
    "wide environmental shot with subject small but clear",
    "close-up detail shot of hands-on work or tools",
    "over-the-shoulder perspective at a desk or workspace",
    "diagonal leading line drawing eye to the main subject",
]

TEXTURE_VARIANTS = [
    "flat clean background, no texture",
    "very subtle dot-grid pattern in background only",
    "soft gradient wash behind the subject",
    "thick left-edge accent colour stripe in brand colour",
    "geometric half-shape behind the subject",
    "natural bokeh background blur",
]

COMPOSITION_VARIANTS = [
    "extra-sharp focal point with cinematic depth of field",
    "wide angle environmental context",
    "intimate close crop on the service moment",
    "elevated angle looking down at workspace",
    "eye-level documentary style",
    "low angle empowering the subject",
]

_INTENT_ARCHETYPE_POOL: dict[str, list[str]] = {
    "transactional": ["OFFER", "URGENCY", "SOCIAL_PROOF"],
    "commercial": ["SOCIAL_PROOF", "AUTHORITY", "DATA_DRIVEN"],
    "informational": ["PROBLEM_SOLVE", "DATA_DRIVEN", "SOCIAL_PROOF"],
}


def infer_keyword_intent(
    keyword: str,
    *,
    search_volume: int | None = None,
    keyword_difficulty: int | None = None,
    cpc: float | None = None,
) -> str:
    """Map Ahrefs-style signals + phrase heuristics to intent."""
    kw = (keyword or "").lower()
    if any(w in kw for w in ("free", "quote", "book now", "deal", "offer", "price", "cost")):
        return "transactional"
    if any(w in kw for w in ("agency", "company", "services", "near me", "hire", "expert", "consultant")):
        return "commercial"
    if cpc is not None and cpc > 15:
        return "commercial"
    if keyword_difficulty is not None and keyword_difficulty < 30:
        return "informational"
    if search_volume is not None and search_volume > 500:
        return "commercial"
    return "informational"


def pick_archetype(
    *,
    keyword: str,
    intent: str,
    last_archetype: str | None,
    used_in_batch: list[str] | None = None,
    post_index: int = 1,
) -> str:
    """Pick next archetype — never repeat back-to-back; prefer intent-matched pool."""
    pool = list(_INTENT_ARCHETYPE_POOL.get(intent, list(AD_ARCHETYPES.keys())))
    used = set(used_in_batch or [])
    candidates = [a for a in pool if a != last_archetype and a not in used]
    if not candidates:
        candidates = [a for a in AD_ARCHETYPES if a != last_archetype]
    if not candidates:
        candidates = list(AD_ARCHETYPES.keys())
    # Rotate through all 6 across a batch using post_index as tie-breaker.
    offset = (post_index - 1) % len(candidates)
    random.shuffle(candidates)
    chosen = candidates[offset % len(candidates)]
    return chosen


def _derive_visual_hook(keyword: str, theme: str, post_body: str, archetype: str) -> str:
    arch = AD_ARCHETYPES.get(archetype, {})
    theme_bit = re.sub(r"\s+", " ", (theme or "").strip())[:120]
    body_bit = re.sub(r"\s+", " ", (post_body or "").strip())[:160]
    if theme_bit:
        return f"Visualise the service moment for '{keyword}': {theme_bit}"
    if body_bit:
        return f"Visualise this post theme for '{keyword}': {body_bit[:100]}"
    return f"Visualise a compelling {keyword} service scene — {arch.get('colour_mood', 'professional')}"


def build_gbp_post_image_prompt(
    *,
    keyword: str,
    business_name: str,
    metro: str = "",
    theme: str = "",
    post_body: str = "",
    brand_config: dict[str, Any] | None = None,
    archetype: str,
    layout: str | None = None,
    texture: str | None = None,
    composition: str | None = None,
    post_index: int = 1,
) -> tuple[str, dict[str, Any]]:
    """Build Runway prompt + metadata for a unique keyword-matched GBP post image."""
    arch = AD_ARCHETYPES.get(archetype, AD_ARCHETYPES["SOCIAL_PROOF"])
    brand = brand_config or {}
    primary_kw = (keyword or "local services").strip()
    bname = (business_name or "local business").strip()
    area = (metro or "").strip()
    primary_colour = str(brand.get("primary_color") or "#2E8B7F").strip()
    secondary_colour = str(brand.get("secondary_color") or "#1A1A2E").strip()

    layout = layout or random.choice(LAYOUT_VARIANTS)
    texture = texture or random.choice(TEXTURE_VARIANTS)
    composition = composition or random.choice(COMPOSITION_VARIANTS)
    visual_hook = _derive_visual_hook(primary_kw, theme, post_body, archetype)
    logo_bg = backdrop_for_archetype(archetype)
    logo_zone = (
        "Keep the top-left corner clean, bright white or very light — no busy detail "
        "(a dark/black Clicktrends logo will be placed here after generation)."
        if logo_bg == "light"
        else
        "Keep the top-left corner clean, dark navy or charcoal — no busy detail "
        "(a white Clicktrends logo will be placed here after generation)."
    )

    area_clause = f" in {area}" if area else ""
    prompt = f"""
Create a unique, professional Google Business Profile post photo for {bname}, a {primary_kw} business{area_clause}.

CORE KEYWORD (the image MUST clearly relate to this service/topic):
"{primary_kw}"

VISUAL HOOK (centrepiece of the composition):
{visual_hook}

CREATIVE ARCHETYPE: {archetype}
VISUAL DIRECTION: {arch["visual_direction"]}
COLOUR MOOD: {arch["colour_mood"]}
Include these visual elements: {", ".join(arch.get("visual_elements") or [])}

COMPOSITION:
- Layout: {layout}
- Background: {texture}
- Camera/style: {composition}
- Brand accent colours: primary {primary_colour}, secondary {secondary_colour} (use subtly in scene/props/lighting, not as flat fills)
- Logo placement zone: {logo_zone}

STRICT RULES:
- NO text, words, letters, logos, watermarks, or UI mockups anywhere in the image
- NO stock-photo clichés: no generic globe, rocket, handshake-in-sunset, or laptop-on-desk-only shots
- NO repeated generic marketing template look — this must feel like a bespoke photo shoot
- Scene must be unmistakably about "{primary_kw}" — a viewer should guess the service from the image alone
- Photorealistic, well-lit, trustworthy local business imagery suitable for Google Maps
- Square 1:1 friendly composition (subject centred or rule-of-thirds)
- Post batch position {post_index} — make this visually distinct from other posts in the same campaign

STYLE REFERENCE: High-end Australian digital agency marketing photography — clean, bold, result-oriented.
NOT: Canva template, clip art, or AI-slop sameness.
""".strip()

    meta = {
        "archetype": archetype,
        "keyword": primary_kw,
        "layout": layout,
        "texture": texture,
        "composition": composition,
        "visual_hook": visual_hook,
        "post_index": post_index,
        "logo_background": logo_bg,
    }
    return prompt, meta


def encode_prompt_meta(meta: dict[str, Any], runway_prompt: str) -> str:
    """Store archetype metadata alongside the Runway prompt in rp_gbp_photos.prompt."""
    return json.dumps({"meta": meta, "prompt": runway_prompt[:4000]}, ensure_ascii=False)


def decode_prompt_meta(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "meta" in data:
            return dict(data.get("meta") or {})
    except json.JSONDecodeError:
        pass
    return {}


async def load_recent_image_history(session: AsyncSession, client_id: str, *, limit: int = 12) -> dict[str, Any]:
    """Load last-used archetypes from recent AI-generated GBP photos."""
    rows = (
        await session.execute(
            text(
                """
                SELECT prompt FROM rp_gbp_photos
                WHERE client_id = :cid
                  AND source IN ('gbp_post', 'runway')
                  AND prompt IS NOT NULL
                ORDER BY created_at DESC
                LIMIT :lim
                """
            ),
            {"cid": client_id, "lim": limit},
        )
    ).scalars().all()

    archetypes: list[str] = []
    layouts: list[str] = []
    for raw in rows:
        meta = decode_prompt_meta(str(raw or ""))
        if meta.get("archetype"):
            archetypes.append(str(meta["archetype"]))
        if meta.get("layout"):
            layouts.append(str(meta["layout"]))

    return {
        "last_archetype": archetypes[0] if archetypes else None,
        "used_archetypes": archetypes,
        "used_layouts": layouts,
        "generation_count": len(archetypes),
    }


def looks_like_full_runway_prompt(theme: str) -> bool:
    """True when the user/AI already supplied a detailed Runway brief."""
    t = (theme or "").strip()
    if len(t) < 180:
        return False
    markers = (
        "CORE KEYWORD",
        "VISUAL HOOK",
        "STRICT RULES",
        "Create a unique, professional Google Business Profile",
        "CREATIVE ARCHETYPE",
    )
    return sum(1 for m in markers if m in t) >= 2


def _archetype_from_prompt_text(text: str) -> str | None:
    match = re.search(r"CREATIVE ARCHETYPE:\s*([A-Z_]+)", text or "", re.I)
    if match:
        arch = match.group(1).upper()
        if arch in AD_ARCHETYPES:
            return arch
    return None


async def build_runway_prompt_for_gbp_post(
    session: AsyncSession,
    client_id: str,
    *,
    keyword: str,
    business_name: str,
    metro: str = "",
    theme: str = "",
    post_body: str = "",
    brand_config: dict[str, Any] | None = None,
    post_index: int = 1,
    post_total: int = 1,
    prior_archetypes: list[str] | None = None,
    search_volume: int | None = None,
    keyword_difficulty: int | None = None,
    cpc: float | None = None,
) -> tuple[str, dict[str, Any]]:
    """End-to-end: pick archetype + build unique Runway prompt for one GBP post image."""
    theme_clean = (theme or "").strip()
    if looks_like_full_runway_prompt(theme_clean):
        arch = _archetype_from_prompt_text(theme_clean) or "SOCIAL_PROOF"
        meta = {
            "archetype": arch,
            "keyword": keyword,
            "layout": "user-supplied",
            "texture": "user-supplied",
            "composition": "user-supplied",
            "visual_hook": "user-supplied",
            "post_index": post_index,
            "logo_background": backdrop_for_archetype(arch),
            "source": "ai_direction",
        }
        return theme_clean[:4000], meta

    history = await load_recent_image_history(session, client_id)
    intent = infer_keyword_intent(
        keyword,
        search_volume=search_volume,
        keyword_difficulty=keyword_difficulty,
        cpc=cpc,
    )
    batch_used = list(prior_archetypes or [])
    archetype = pick_archetype(
        keyword=keyword,
        intent=intent,
        last_archetype=history.get("last_archetype"),
        used_in_batch=batch_used,
        post_index=post_index,
    )

    used_layouts = set(history.get("used_layouts") or [])
    layout_pool = [l for l in LAYOUT_VARIANTS if l not in used_layouts] or LAYOUT_VARIANTS
    layout = random.choice(layout_pool)

    prompt, meta = build_gbp_post_image_prompt(
        keyword=keyword,
        business_name=business_name,
        metro=metro,
        theme=theme,
        post_body=post_body,
        brand_config=brand_config,
        archetype=archetype,
        layout=layout,
        post_index=post_index,
    )
    meta["intent"] = intent
    meta["post_total"] = post_total
    return prompt, meta
