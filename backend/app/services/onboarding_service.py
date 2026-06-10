"""Save client profile + seed suburb grid on first-time onboarding."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.au_suburbs import get_suburbs_for_metro
from app.lib.primary_keywords import normalize_primary_keywords

logger = logging.getLogger(__name__)


def _norm_site_url(u: str) -> str:
    s = (u or "").strip().rstrip("/").lower()
    if s.startswith("https://"):
        s = s[8:]
    elif s.startswith("http://"):
        s = s[7:]
    if s.startswith("www."):
        s = s[4:]
    return s


class OnboardingService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def save_profile(
        self,
        client_id: UUID,
        *,
        business_name: str,
        business_url: str,
        business_address: str = "",
        business_phone: str = "",
        primary_keyword: str,
        metro_label: str,
        search_radius_km: int = 25,
        location_scope: str = "suburb",
        primary_suburb: str = "",
    ) -> dict:
        """Update rp_clients profile and (re-)seed suburb grid."""
        # Clean URL
        url = business_url.strip().rstrip("/")
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url

        scope = (location_scope or "suburb").strip().lower()
        if scope not in ("city", "suburb"):
            scope = "suburb"
        anchor_suburb = (primary_suburb or "").strip()
        sr = max(5, min(100, int(search_radius_km))) if scope == "suburb" else 100
        address = (business_address or "").strip()
        phone = (business_phone or "").strip()
        kw = normalize_primary_keywords(primary_keyword or "")
        metro = (metro_label or "").strip()

        prev = (
            await self._session.execute(
                text(
                    """
                    SELECT business_url, primary_keyword, metro_label,
                           COALESCE(search_radius_km, 25) AS search_radius_km,
                           COALESCE(location_scope, 'suburb') AS location_scope,
                           COALESCE(primary_suburb, '') AS primary_suburb
                    FROM rp_clients
                    WHERE client_id = :cid
                    """
                ),
                {"cid": str(client_id)},
            )
        ).mappings().first()

        old_url = _norm_site_url(str(prev["business_url"] if prev else ""))
        old_kw = str(prev["primary_keyword"] if prev else "").strip().lower()
        old_metro = str(prev["metro_label"] if prev else "").strip().lower()
        old_sr = int(prev["search_radius_km"]) if prev else sr
        old_scope = str(prev["location_scope"] if prev else "suburb").strip().lower()
        old_anchor = str(prev["primary_suburb"] if prev else "").strip().lower()

        new_url = _norm_site_url(url)
        new_kw = kw.lower()
        new_metro = metro.lower()
        new_anchor = anchor_suburb.lower()
        profile_changed = (
            new_url != old_url
            or new_kw != old_kw
            or new_metro != old_metro
            or scope != old_scope
            or new_anchor != old_anchor
        )
        grid_changed = (
            new_metro != old_metro
            or sr != old_sr
            or scope != old_scope
            or new_anchor != old_anchor
        )

        await self._session.execute(
            text(
                """
                UPDATE rp_clients
                SET business_name    = :bname,
                    business_url     = :burl,
                    business_address = :baddr,
                    business_phone   = :bphone,
                    primary_keyword  = :kw,
                    metro_label      = :metro,
                    location_scope   = :scope,
                    primary_suburb   = :anchor,
                    search_radius_km = :sr,
                    updated_at       = now()
                WHERE client_id = :cid
                """
            ),
            {
                "bname": business_name,
                "burl": url,
                "baddr": address,
                "bphone": phone,
                "kw": kw,
                "metro": metro,
                "scope": scope,
                "anchor": anchor_suburb,
                "sr": sr,
                "cid": str(client_id),
            },
        )

        # Only wipe GBP posts / content queue when keyword, site, or metro actually change —
        # re-saving onboarding after login must not delete existing drafts.
        if profile_changed:
            await self._session.execute(
                text("DELETE FROM rp_content_queue WHERE client_id = :cid"),
                {"cid": str(client_id)},
            )
            logger.info("Onboarding: cleared content queue for %s (profile changed)", client_id)

        grid_count = (
            await self._session.execute(
                text("SELECT COUNT(*) AS n FROM rp_suburb_grid WHERE client_id = :cid"),
                {"cid": str(client_id)},
            )
        ).mappings().first()
        has_grid = int(grid_count["n"] if grid_count else 0) > 0

        if grid_changed or not has_grid:
            await self._session.execute(
                text("DELETE FROM rp_suburb_grid WHERE client_id = :cid"),
                {"cid": str(client_id)},
            )
        else:
            # Refresh grid from expanded suburb catalog (e.g. more Melbourne suburbs) without metro/radius change
            catalog = get_suburbs_for_metro(
                metro,
                radius_km=sr,
                location_scope=scope,
                primary_suburb=anchor_suburb or None,
            )
            existing = (
                await self._session.execute(
                    text("SELECT COUNT(*) AS n FROM rp_suburb_grid WHERE client_id = :cid"),
                    {"cid": str(client_id)},
                )
            ).scalar() or 0
            if len(catalog) > int(existing):
                await self._session.execute(
                    text("DELETE FROM rp_suburb_grid WHERE client_id = :cid"),
                    {"cid": str(client_id)},
                )
                grid_changed = True

        from uuid6 import uuid7  # noqa: PLC0415

        suburbs = get_suburbs_for_metro(
            metro,
            radius_km=sr,
            location_scope=scope,
            primary_suburb=anchor_suburb or None,
        )
        for priority, s in enumerate(suburbs, start=1):
            await self._session.execute(
                text(
                    """
                    INSERT INTO rp_suburb_grid
                        (id, client_id, suburb, state, postcode, lat, lng, population, rank_priority)
                    VALUES (:id, :cid, :suburb, :state, :postcode, :lat, :lng, :pop, :pri)
                    ON CONFLICT (client_id, suburb, postcode) DO UPDATE
                        SET rank_priority = EXCLUDED.rank_priority,
                            updated_at    = now()
                    """
                ),
                {
                    "id": str(uuid7()),
                    "cid": str(client_id),
                    "suburb": s["suburb"],
                    "state": s["state"],
                    "postcode": s["postcode"],
                    "lat": s["lat"],
                    "lng": s["lng"],
                    "pop": s["population"],
                    "pri": priority,
                },
            )

        await self._session.commit()
        logger.info(
            "Onboarding saved for %s: %d suburbs seeded (%s)",
            str(client_id), len(suburbs), metro_label,
        )
        return {
            "suburbs_seeded": len(suburbs),
            "metro_label": metro,
            "profile_changed": profile_changed,
            "grid_changed": grid_changed,
        }
