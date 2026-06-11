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


class SiteKeywordItem(BaseModel):
    keyword: str
    volume: int | None = None
    volume_display: str = "—"
    difficulty: int | None = None
    competition: str | None = None
    best_position: int | None = None
    traffic: int | None = None
    ranking_url: str | None = None
    opportunity_score: int = 0


class SiteKeywordsResponse(BaseModel):
    target: str
    country: str = "au"
    country_label: str = "Australia"
    keywords: list[SiteKeywordItem] = Field(default_factory=list)
    source: str = "ahrefs"
    message: str | None = None
    from_cache: bool = False
    cached_at: str | None = None
    cache_expires_at: str | None = None


class SerpCompetitorItem(BaseModel):
    position: int | None = None
    domain: str
    url: str
    title: str | None = None
    traffic: int | None = None
    in_local_pack: bool = False
    local_pack_position: int | None = None


class KeywordSerpCompetitorsResponse(BaseModel):
    keyword: str
    country: str = "au"
    competitors: list[SerpCompetitorItem] = Field(default_factory=list)
    source: str = "ahrefs"
    message: str | None = None
    from_cache: bool = False
    cached_at: str | None = None
    cache_expires_at: str | None = None


class CompetitorGbpPost(BaseModel):
    text: str
    date: str | None = None
    url: str | None = None
    mentions_keyword: bool = False


class CompetitorGbpPostsItem(BaseModel):
    business_name: str
    domain: str | None = None
    organic_rank: int | None = None
    maps_rank: int | None = None
    in_local_pack: bool = False
    local_pack_position: int | None = None
    posts_count: int = 0
    first_post_date: str | None = None
    last_post_date: str | None = None
    posts_per_month: float | None = None
    keyword_mentions: int = 0
    top_terms: list[str] = Field(default_factory=list)
    recent_posts: list[CompetitorGbpPost] = Field(default_factory=list)
    note: str | None = None


class CompetitorGbpPostsResponse(BaseModel):
    keyword: str
    competitors: list[CompetitorGbpPostsItem] = Field(default_factory=list)
    competitor_source: str = "organic_serp"
    source: str = "dataforseo"
    message: str | None = None
    from_cache: bool = False
    cached_at: str | None = None
    cache_expires_at: str | None = None


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
