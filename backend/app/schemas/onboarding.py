from pydantic import BaseModel, Field, field_validator

from app.lib.primary_keywords import normalize_primary_keywords, parse_primary_keywords


class OnboardingRequest(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    business_url: str = Field(min_length=4, max_length=500)
    business_address: str = Field(default="", max_length=500)
    business_phone: str = Field(default="", max_length=50)
    primary_keyword: str = Field(min_length=2, max_length=1000)

    @field_validator("primary_keyword")
    @classmethod
    def normalize_primary_keyword(cls, v: str) -> str:
        normalized = normalize_primary_keywords(v)
        if not normalized:
            raise ValueError("Enter at least one primary service keyword")
        if len(parse_primary_keywords(normalized)) > 12:
            raise ValueError("Maximum 12 primary keywords")
        return normalized
    metro_label: str = Field(min_length=2, max_length=100)
    location_scope: str = Field(default="suburb", pattern="^(city|suburb)$")
    primary_suburb: str = Field(default="", max_length=120)
    search_radius_km: int = Field(default=25, ge=5, le=100)


class OnboardingResponse(BaseModel):
    suburbs_seeded: int
    metro_label: str
    message: str
