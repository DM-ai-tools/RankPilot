from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.dashboard import ScoreBlock


class DashboardScoresPart(BaseModel):
    seo_visibility: ScoreBlock


class StatBlock(BaseModel):
    visibility_score: float
    visibility_delta: float | None = None
    suburbs_ranked: int
    suburbs_total: int
    monthly_searches: int
    monthly_volume_note: str | None = Field(
        default=None,
        description="How monthly_searches was derived (one state vs estimate), for dashboard copy",
    )
    missed_suburbs: int
    missed_note: str | None = None


class GaugeBlock(BaseModel):
    top3_count: int
    page1_count: int = Field(description="Ranks 4–10 in the Maps / local pack")
    pack_11_20_count: int = Field(description="Ranks 11–20 (still visible)")
    not_ranking_count: int = Field(description="No rank or rank > 20")
    top3_pct: int
    page1_pct: int
    pack_11_20_pct: int
    not_ranking_pct: int


class ActivityItem(BaseModel):
    icon: str
    heading: str
    detail: str
    occurred_at: datetime


class RankWinRow(BaseModel):
    suburb: str
    before_rank: int | None
    after_rank: int | None
    change_label: str


class RecommendationRow(BaseModel):
    icon: str
    title: str
    subtitle: str
    priority: str  # high | med | low


class BusinessProfileBlock(BaseModel):
    name: str
    address: str
    phone: str
    maps_url: str
    source: str


class DashboardOverviewResponse(BaseModel):
    scores: DashboardScoresPart
    week_label: str
    keyword: str
    metro_label: str
    business_profile: BusinessProfileBlock | None = None
    stats: StatBlock
    gauge: GaugeBlock
    activity: list[ActivityItem]
    rank_wins: list[RankWinRow]
    recommendations: list[RecommendationRow]
