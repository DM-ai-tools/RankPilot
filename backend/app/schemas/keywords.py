"""Keyword research schemas (Ahrefs)."""

from pydantic import BaseModel, Field


class SuburbKeywordPhrase(BaseModel):
    keyword: str
    suburb: str
    state: str | None = None
    avg_monthly_searches: int = 0
    competition: str | None = None
    difficulty: int | None = None
    opportunity_score: int = 0
    traffic_potential: int | None = None


class RelatedKeywordIdea(BaseModel):
    keyword: str
    suburb: str | None = None
    avg_monthly_searches: int = 0
    competition: str | None = None
    difficulty: int | None = None
    opportunity_score: int = 0
    traffic_potential: int | None = None


class SuburbKeywordResearchResponse(BaseModel):
    primary_keyword: str = ""
    metro_label: str = ""
    geo_label: str = ""
    location_scope: str = "suburb"
    suburbs: list[str] = Field(default_factory=list)
    suburb_phrases: list[SuburbKeywordPhrase] = Field(default_factory=list)
    related_ideas: list[RelatedKeywordIdea] = Field(default_factory=list)
    top_keywords: list[RelatedKeywordIdea] = Field(
        default_factory=list,
        description="Live Ahrefs-ranked local keywords (best for GBP posts/description)",
    )
    source: str = "ahrefs"
    message: str | None = None
    from_cache: bool = False
    cached_at: str | None = None
    cache_expires_at: str | None = None


class KeywordLookupItem(BaseModel):
    keyword: str
    volume: int = 0
    difficulty: int | None = None
    competition: str | None = None
    traffic_potential: int | None = None
    cpc_cents: int | None = None
    opportunity_score: int = 0


class KeywordLookupResponse(BaseModel):
    country: str = "au"
    keywords: list[KeywordLookupItem] = Field(default_factory=list)
    source: str = "ahrefs"
    message: str | None = None
    from_cache: bool = False
    cached_at: str | None = None
    cache_expires_at: str | None = None


class KeywordIdeaItem(BaseModel):
    keyword: str
    volume: int | None = None
    volume_display: str = "—"
    difficulty: int | None = None
    competition: str | None = None


class GlobalVolumeCountry(BaseModel):
    country_code: str
    country_name: str
    volume: int
    share_pct: int = 100


class KeywordOverviewMetrics(BaseModel):
    keyword: str
    volume: int | None = None
    volume_display: str = "—"
    difficulty: int | None = None
    difficulty_label: str | None = None
    difficulty_short: str = "N/A"
    kd_description: str = ""
    traffic_potential: int | None = None
    global_volume: int | None = None
    volume_chart: list[int] = Field(default_factory=list)
    global_by_country: list[GlobalVolumeCountry] = Field(default_factory=list)


class KeywordOverviewResponse(BaseModel):
    keyword: str
    country: str = "au"
    country_label: str = "Australia"
    metrics: KeywordOverviewMetrics | None = None
    terms_match: list[KeywordIdeaItem] = Field(default_factory=list)
    questions: list[KeywordIdeaItem] = Field(default_factory=list)
    also_rank_for: list[KeywordIdeaItem] = Field(default_factory=list)
    also_talk_about: list[KeywordIdeaItem] = Field(default_factory=list)
    source: str = "ahrefs"
    message: str | None = None
    from_cache: bool = False
    cached_at: str | None = None
    cache_expires_at: str | None = None
