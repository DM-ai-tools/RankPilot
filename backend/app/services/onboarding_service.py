"""Save client profile + seed suburb grid on first-time onboarding."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.au_suburbs import get_suburbs_for_metro

logger = logging.getLogger(__name__)


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
    ) -> dict:
        """Update rp_clients profile and (re-)seed suburb grid."""
        # Clean URL
        url = business_url.strip().rstrip("/")
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url

        sr = max(5, min(100, int(search_radius_km)))
        address = (business_address or "").strip()
        phone = (business_phone or "").strip()
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
                "kw": primary_keyword,
                "metro": metro_label,
                "sr": sr,
                "cid": str(client_id),
            },
        )

        # Clear stale auto-generated queue (e.g. old "pest control …" demo titles) when profile changes
        await self._session.execute(
            text("DELETE FROM rp_content_queue WHERE client_id = :cid"),
            {"cid": str(client_id)},
        )

        # Clear old suburb grid and re-seed for the new metro
        await self._session.execute(
            text("DELETE FROM rp_suburb_grid WHERE client_id = :cid"),
            {"cid": str(client_id)},
        )

        suburbs = get_suburbs_for_metro(metro_label, radius_km=sr)
        from uuid6 import uuid7  # noqa: PLC0415

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
        return {"suburbs_seeded": len(suburbs), "metro_label": metro_label}
