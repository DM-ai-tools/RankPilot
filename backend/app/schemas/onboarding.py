from pydantic import BaseModel, Field


class OnboardingRequest(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    business_url: str = Field(min_length=4, max_length=500)
    business_address: str = Field(default="", max_length=500)
    business_phone: str = Field(default="", max_length=50)
    primary_keyword: str = Field(min_length=2, max_length=200)
    metro_label: str = Field(min_length=2, max_length=100)
    search_radius_km: int = Field(default=25, ge=5, le=100)


class OnboardingResponse(BaseModel):
    suburbs_seeded: int
    metro_label: str
    message: str
