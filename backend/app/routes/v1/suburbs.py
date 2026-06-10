"""Suburb grid helpers — GeoJSON boundaries for map rendering."""

from pydantic import BaseModel, Field

from fastapi import APIRouter, Query

from app.data.au_suburbs import list_metro_suburb_names
from app.deps import CurrentClientId, DbSession
from app.services.suburb_geo_service import fetch_suburb_geo

router = APIRouter()


@router.get("/catalog")
async def suburb_catalog(metro_label: str = Query(..., min_length=2)) -> dict:
    """Suburb names for onboarding suburb picker."""
    names = list_metro_suburb_names(metro_label)
    return {"metro_label": metro_label, "suburbs": names}


class SuburbGeoRequest(BaseModel):
    suburb_ids: list[str] = Field(default_factory=list, max_length=100)


@router.post("/geo")
async def suburb_geo(body: SuburbGeoRequest, client_id: CurrentClientId, session: DbSession) -> dict:
    """GeoJSON polygon (or hex fallback) per suburb in the client's grid."""
    return await fetch_suburb_geo(session, client_id, body.suburb_ids)
