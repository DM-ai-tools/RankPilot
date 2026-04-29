from uuid import UUID

from pydantic import BaseModel


class OpportunityRow(BaseModel):
    suburb_id: UUID
    suburb: str
    postcode: str | None
    population: int | None
    rank_position: int | None
    band: str  # "page2" | "not_ranking"
    recommended_action: str


class OpportunitiesResponse(BaseModel):
    items: list[OpportunityRow]
