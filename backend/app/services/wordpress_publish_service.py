"""Publish RankPilot queue items to WordPress via REST (Application Password)."""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlparse
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _slugify(title: str, max_len: int = 80) -> str:
    s = (title or "").lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[-\s]+", "-", s).strip("-")
    return (s[:max_len] if s else "landing-page") or "landing-page"


def _slug_from_target_hint(hint: str | None) -> str | None:
    if not hint or not isinstance(hint, str):
        return None
    raw = hint.strip().rstrip("/")
    if not raw:
        return None
    path = urlparse(raw).path.strip("/")
    if path:
        seg = path.split("/")[-1]
        if seg:
            return re.sub(r"[^\w-]", "", seg.lower())[:80] or None
    return None


def _normalize_site(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    if u and not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u


async def publish_landing_page_to_wordpress(
    session: AsyncSession,
    client_id: UUID,
    *,
    title: str,
    body: str,
    target_url_hint: str | None = None,
) -> str:
    """
    Create a published **Page** on the client's WordPress site (wp-admin → Pages).
    Returns the public permalink (``link`` from WP JSON).
    """
    row = (
        await session.execute(
            text(
                """
                SELECT access_token, extra_data
                FROM rp_integrations
                WHERE client_id = :cid AND type = 'wordpress'
                LIMIT 1
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WordPress is not connected. Add it from Onboarding (Connect WordPress) with an Application Password.",
        )

    app_password = str(row["access_token"] or "").strip()
    extra = row["extra_data"]
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except json.JSONDecodeError:
            extra = {}
    if not isinstance(extra, dict):
        extra = {}
    site = _normalize_site(str(extra.get("site_url") or ""))
    wp_user = str(extra.get("username") or "").strip()
    if not site or not wp_user or not app_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WordPress integration is incomplete. Re-connect WordPress from Onboarding.",
        )

    slug = _slug_from_target_hint(target_url_hint) or _slugify(title)
    html = (body or "").strip()
    if not html:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot publish an empty page body.")

    # If model returned plain text / markdown without HTML tags, wrap so WP renders predictably.
    if "<" not in html[:500]:
        import html as html_lib

        parts = [f"<p>{html_lib.escape(p.strip())}</p>" for p in re.split(r"\n\s*\n", html) if p.strip()]
        html = "\n".join(parts) if parts else f"<p>{html_lib.escape(html)}</p>"

    url = f"{site}/wp-json/wp/v2/pages"
    headers = {
        "User-Agent": "RankPilot/1.0 (WordPress page publish)",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload: dict = {"title": title, "content": html, "status": "publish", "slug": slug}

    async with httpx.AsyncClient(timeout=45, follow_redirects=True) as http:
        for attempt in range(3):
            r = await http.post(
                url,
                json=payload,
                auth=(wp_user, app_password),
                headers=headers,
            )
            if r.status_code in (200, 201):
                data = r.json()
                link = str(data.get("link") or "").strip()
                if not link:
                    link = f"{site}/?page_id={data.get('id', '')}"
                return link
            if r.status_code in (400, 409) and attempt < 2:
                payload["slug"] = f"{slug}-rankpilot-{attempt + 2}"
                continue
            detail = r.text[:400] if r.text else r.reason_phrase
            if r.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="WordPress rejected credentials when publishing. Re-create an Application Password and reconnect WordPress.",
                ) from None
            if r.status_code == 403:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="WordPress returned Forbidden when creating the page. Check the user can publish pages and REST is not blocked.",
                ) from None
            logger.warning("WordPress publish failed HTTP %s: %s", r.status_code, detail)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"WordPress publish failed ({r.status_code}): {detail}",
            ) from None
