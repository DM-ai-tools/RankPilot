"""L4 response shapes for dashboard — SEO visibility only."""

from pydantic import BaseModel, Field


class ScoreBlock(BaseModel):
    value: float = Field(ge=0, le=100)
    delta_4w: float | None = None


class DashboardScoresResponse(BaseModel):
    seo_visibility: ScoreBlock
    week_label: str
