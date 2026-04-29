"""Generate landing-page / GBP content via Claude and queue it in rp_content_queue."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import UUID

import anthropic
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.data.au_suburbs import get_suburbs_for_metro

logger = logging.getLogger(__name__)


async def _get_client_profile(session: AsyncSession, client_id: UUID) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT business_name, business_url, primary_keyword, metro_label
                FROM rp_clients
                WHERE client_id = :cid
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    return dict(row) if row else {}


async def _get_top_suburbs(session: AsyncSession, client_id: UUID, limit: int = 3) -> list[str]:
    rows = (
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
            {"cid": str(client_id), "lim": limit},
        )
    ).mappings().all()
    return [f"{r['suburb']}, {r['state']}" for r in rows]


def _claude_model() -> str:
    """Default Claude Sonnet 4.6; override with ANTHROPIC_CONTENT_MODEL in backend/.env."""
    return (get_settings().anthropic_content_model or "claude-sonnet-4-6").strip()


def _call_claude(prompt: str, api_key: str) -> str:
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=_claude_model(),
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def _business_from_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    host = urlparse(raw).netloc.lower()
    host = re.sub(r"^www\.", "", host)
    parts = [p for p in host.split(".") if p]
    if not parts:
        return ""
    ignore = {"com", "au", "net", "org", "co"}
    for p in parts:
        if p not in ignore:
            return p.replace("-", " ").title()
    return parts[0].replace("-", " ").title()


def _canon(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


async def generate_content_for_client(session: AsyncSession, client_id: UUID) -> dict:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return {"error": "ANTHROPIC_API_KEY is not set in backend/.env"}

    profile = await _get_client_profile(session, client_id)
    if not profile.get("business_name"):
        return {"error": "Complete your onboarding first (Settings → Onboarding)."}

    bname   = str(profile["business_name"] or "").strip()
    burl    = str(profile.get("business_url") or "").strip()
    url_brand = _business_from_url(burl)
    prompt_business = bname
    # If dashboard URL/keyword changed but onboarding name stayed old, trust website brand for prompts.
    if url_brand and (not bname or (_canon(url_brand) not in _canon(bname) and _canon(bname) not in _canon(url_brand))):
        prompt_business = url_brand
    keyword = profile.get("primary_keyword") or prompt_business or bname
    metro = profile.get("metro_label") or "your city"

    from uuid6 import uuid7  # noqa: PLC0415

    await session.execute(
        text("DELETE FROM rp_content_queue WHERE client_id = :cid"),
        {"cid": str(client_id)},
    )

    suburbs = await _get_top_suburbs(session, client_id, limit=3)
    if not suburbs:
        suburbs = [
            f"{s['suburb']}, {s['state']}"
            for s in get_suburbs_for_metro(metro)[:3]
        ]

    if not suburbs:
        return {
            "error": "No suburbs to target — run onboarding and pick a metro, or run a Maps scan to seed the grid.",
            "generated": 0,
            "items": [],
        }

    generated: list[dict] = []
    errors: list[str] = []
    now = datetime.now(UTC)

    # ── 1. Landing pages for top suburbs ─────────────────────────────────────
    for suburb in suburbs:
        prompt = (
            f"You are an SEO copywriter for an Australian local business.\n\n"
            f"Business: {prompt_business or bname}\n"
            f"Service keyword: {keyword}\n"
            f"Location: {suburb}\n"
            f"Website: {burl}\n\n"
            f"Write a compelling, SEO-optimised landing page (approx 400 words) targeting "
            f"'{keyword} {suburb}'. Include:\n"
            f"- An H1 heading\n"
            f"- 2–3 short paragraphs covering the service benefit, local trust signals, and a CTA\n"
            f"- A bullet list of 4–5 key services\n\n"
            f"Return ONLY the page body text (no HTML tags)."
        )
        logger.info("Generating landing page for %s in %s", prompt_business or bname, suburb)
        try:
            body = _call_claude(prompt, settings.anthropic_api_key)
        except Exception as exc:  # noqa: BLE001
            logger.error("Claude error for %s: %s", suburb, exc)
            errors.append(f"{suburb}: {exc!s}")
            continue

        body = (body or "").strip()
        if not body:
            errors.append(f"{suburb}: empty response from model {_claude_model()}")
            continue

        suburb_slug = suburb.replace(", ", "-").replace(" ", "-").lower()
        wc = len(body.split())
        item_id = str(uuid7())
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
                "id":      item_id,
                "cid":     str(client_id),
                "now":     now,
                "payload": __import__("json").dumps({
                    "title":      f"{keyword.title()} {suburb} — Landing Page",
                    "body":       body,
                    "word_count": wc,
                    "notes":      f"Auto-generated for suburb: {suburb}",
                    "target_url": f"{burl}/{suburb_slug}/" if burl else "",
                }),
            },
        )
        generated.append({"type": "landing_page", "suburb": suburb, "words": wc})

    # ── 2. GBP description ────────────────────────────────────────────────────
    suburb_list = ", ".join(suburbs) if suburbs else metro
    gbp_prompt = (
        f"Write a Google Business Profile description (max 750 characters) for:\n\n"
        f"Business: {prompt_business or bname}\n"
        f"Service: {keyword}\n"
        f"Service areas: {suburb_list}\n\n"
        f"Make it compelling, keyword-rich, and end with a call-to-action."
    )
    logger.info("Generating GBP description for %s", prompt_business or bname)
    try:
        gbp_body = _call_claude(gbp_prompt, settings.anthropic_api_key).strip()
    except Exception as exc:  # noqa: BLE001
        logger.error("Claude GBP error: %s", exc)
        errors.append(f"GBP description: {exc!s}")
        gbp_body = ""

    if gbp_body:
        gbp_id = str(uuid7())
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
                "id":      gbp_id,
                "cid":     str(client_id),
                "now":     now,
                "payload": __import__("json").dumps({
                    "title":      f"GBP Description — {prompt_business or bname}",
                    "body":       gbp_body,
                    "word_count": len(gbp_body.split()),
                    "notes":      "Google Business Profile short description (≤750 chars)",
                }),
            },
        )
        generated.append({"type": "gbp_description", "words": len(gbp_body.split())})

    logger.info("Content generation complete: %d items for client %s", len(generated), client_id)

    out: dict = {"generated": len(generated), "items": generated}
    if errors:
        out["warnings"] = errors
    if not generated:
        out["error"] = (
            errors[0]
            if errors
            else "Claude returned no usable text — check ANTHROPIC_API_KEY and model name."
        )
    return out
