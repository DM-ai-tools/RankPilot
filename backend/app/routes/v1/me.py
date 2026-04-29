"""Current tenant profile + onboarding."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text

from app.deps import CurrentClientId, DbSession
from app.schemas.client import ClientMeResponse
from app.schemas.me_patch import MePatchRequest
from app.schemas.onboarding import OnboardingRequest, OnboardingResponse
from app.services.geocode_service import resolve_business_map_point
from app.services.onboarding_service import OnboardingService

router = APIRouter()


def _norm_site_url(u: str) -> str:
    s = (u or "").strip().rstrip("/").lower()
    if s.startswith("https://"):
        s = s[8:]
    elif s.startswith("http://"):
        s = s[7:]
    if s.startswith("www."):
        s = s[4:]
    return s


@router.get("/me", response_model=ClientMeResponse)
async def get_me(client_id: CurrentClientId, session: DbSession) -> ClientMeResponse:
    row = (
        await session.execute(
            text(
                """
                SELECT client_id, email, business_name, business_url, business_address, business_phone,
                       tier, plan, primary_keyword, metro_label,
                       COALESCE(search_radius_km, 25) AS search_radius_km
                FROM rp_clients
                WHERE client_id = :cid
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    baddr = str(row["business_address"] or "")
    bname = str(row["business_name"] or "")
    metro = str(row["metro_label"] or "")
    map_pt = await resolve_business_map_point(
        business_address=baddr,
        business_name=bname,
        metro_label=metro,
    )
    if map_pt:
        blat, blng, loc_src = map_pt[0], map_pt[1], map_pt[2]
    else:
        blat, blng, loc_src = None, None, None

    return ClientMeResponse(
        client_id=row["client_id"],
        email=str(row["email"]),
        business_name=bname,
        business_url=str(row["business_url"] or ""),
        business_address=baddr,
        business_phone=str(row["business_phone"] or ""),
        tier=str(row["tier"]),
        plan=str(row["plan"]) if row["plan"] else None,
        primary_keyword=str(row["primary_keyword"] or ""),
        metro_label=metro,
        search_radius_km=int(row["search_radius_km"] or 25),
        business_lat=blat,
        business_lng=blng,
        business_location_source=loc_src,
    )


@router.patch("/me", response_model=ClientMeResponse)
async def patch_me(
    body: MePatchRequest,
    client_id: CurrentClientId,
    session: DbSession,
) -> ClientMeResponse:
    """Update website URL (and optionally keyword) before running a visibility scan."""
    prev = (
        await session.execute(
            text(
                "SELECT primary_keyword, business_url FROM rp_clients WHERE client_id = :cid"
            ),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    if not prev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    old_kw = str(prev["primary_keyword"] or "").strip().lower()
    old_site = _norm_site_url(str(prev["business_url"] or ""))

    url = body.business_url.strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    new_site = _norm_site_url(url)
    new_kw = body.primary_keyword.strip().lower() if body.primary_keyword is not None else old_kw

    site_changed = new_site != old_site
    kw_changed = body.primary_keyword is not None and new_kw != old_kw
    if site_changed or kw_changed:
        await session.execute(
            text("DELETE FROM rp_content_queue WHERE client_id = :cid"),
            {"cid": str(client_id)},
        )

    if body.primary_keyword is not None:
        await session.execute(
            text(
                """
                UPDATE rp_clients
                SET business_url = :url,
                    primary_keyword = :kw,
                    updated_at = now()
                WHERE client_id = :cid
                """
            ),
            {"url": url, "kw": body.primary_keyword.strip(), "cid": str(client_id)},
        )
    else:
        await session.execute(
            text(
                """
                UPDATE rp_clients
                SET business_url = :url, updated_at = now()
                WHERE client_id = :cid
                """
            ),
            {"url": url, "cid": str(client_id)},
        )
    return await get_me(client_id, session)


@router.post("/me/onboard", response_model=OnboardingResponse)
async def onboard(
    body: OnboardingRequest,
    client_id: CurrentClientId,
    session: DbSession,
) -> OnboardingResponse:
    """Save business profile and seed suburb grid. Triggers on first setup or whenever you change keyword/city."""
    svc = OnboardingService(session)
    result = await svc.save_profile(
        client_id,
        business_name=body.business_name,
        business_url=body.business_url,
        business_address=body.business_address,
        business_phone=body.business_phone,
        primary_keyword=body.primary_keyword,
        metro_label=body.metro_label,
        search_radius_km=body.search_radius_km,
    )
    return OnboardingResponse(
        suburbs_seeded=result["suburbs_seeded"],
        metro_label=result["metro_label"],
        message=f"Profile saved. {result['suburbs_seeded']} suburbs loaded for {result['metro_label']}. Run a scan to fetch live rankings.",
    )
