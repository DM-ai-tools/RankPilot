from pydantic import BaseModel, Field


class CompetitorVelocityItem(BaseModel):
    title: str
    domain: str | None = None
    reviews_count: int | None = None
    rating: float | None = None
    estimated_monthly: int | None = Field(
        None,
        description="reviews_count / 12 — rough 1-year average velocity estimate",
    )
    is_client: bool = False


class CompetitorVelocityResponse(BaseModel):
    client_title: str | None = None
    client_reviews_total: int | None = None
    client_new_this_month: int = 0
    competitors: list[CompetitorVelocityItem] = Field(default_factory=list)
    note: str | None = None


class ReviewItemRow(BaseModel):
    rating: float | None = None
    review_text: str = ""
    timestamp: str | None = None
    profile_name: str | None = None
    time_ago: str | None = None


class ReviewsSummaryResponse(BaseModel):
    business_title: str | None = Field(None, description="Google listing title from SERP")
    reviews_total_google: int | None = Field(None, description="Total reviews count shown on Google for listing")
    average_rating: float | None = None
    new_this_month: int = Field(0, description="Reviews in returned batch with timestamp in current UTC month")
    items_returned: int = Field(0, description="Number of review rows in this API response (depth-limited)")
    reviews: list[ReviewItemRow] = Field(default_factory=list)
    fetched_at: str | None = None
    message: str | None = Field(None, description="Empty data / missing credentials / upstream error hint")
