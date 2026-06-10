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
    monthly_volume_proxy: int = Field(description="Monthly search volume from Ahrefs for '{keyword} {suburb}'")


class MapPackPlace(BaseModel):
    """One business in the Google Maps local SERP (coordinates from DataForSEO advanced Maps)."""

    title: str
    lat: float
    lng: float
    rank: int | None = Field(
        default=None,
        description="Best pack position when seen in one suburb; same as pack_rank_best when suburb_scan_count=1",
    )
    pack_rank_best: int | None = Field(
        default=None,
        description="Lowest (best) pack position across suburb scans for this outlet",
    )
    pack_rank_worst: int | None = Field(
        default=None,
        description="Highest (worst) pack position across suburb scans for this outlet",
    )
    suburb_scan_count: int = Field(
        default=1,
        description="How many suburb SERP snapshots included this outlet",
    )
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
    volume_source: str = Field(
        default="none",
        description="Source of monthly_volume_proxy on keyword pages: ahrefs | none | ahrefs_error",
    )
