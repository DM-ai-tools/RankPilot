from uuid import UUID

from pydantic import BaseModel, Field


class SuburbRankRow(BaseModel):
    suburb_id: UUID
    suburb: str
    state: str | None = None
    postcode: str | None
    lat: float | None
    lng: float | None
    population: int | None
    rank_position: int | None
    monthly_volume_proxy: int = Field(description="Monthly keyword searches (state-wise via DataForSEO; population fallback)")


class MapPackPlace(BaseModel):
    """One business in the Google Maps local SERP (coordinates from DataForSEO advanced Maps)."""

    title: str
    lat: float
    lng: float
    rank: int | None = None
    domain: str | None = None
    url: str | None = None
    address: str | None = None
    suburb_context: str | None = Field(default=None, description="Suburb grid point whose SERP produced this row")


class SuburbRanksResponse(BaseModel):
    keyword: str
    metro_label: str
    suburbs: list[SuburbRankRow]
    visibility_score: float
    top3_count: int
    page1_count: int
    pack_11_20_count: int
    not_ranking_count: int
    map_competitors: list[MapPackPlace] = Field(
        default_factory=list,
        description="Deduped Maps pack listings with lat/lng from latest stored SERP snapshots",
    )
