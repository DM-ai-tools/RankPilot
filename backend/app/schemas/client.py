from uuid import UUID

from pydantic import BaseModel


class ClientMeResponse(BaseModel):
    client_id: UUID
    email: str
    business_name: str
    business_url: str = ""
    business_address: str = ""
    business_phone: str = ""
    tier: str
    plan: str | None
    primary_keyword: str
    metro_label: str
    search_radius_km: int = 25
    # Map anchor (Nominatim / Google Places / metro CBD fallback).
    business_lat: float | None = None
    business_lng: float | None = None
    business_location_source: str | None = None
