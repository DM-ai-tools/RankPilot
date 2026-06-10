from pydantic import BaseModel, Field, field_validator

from app.lib.primary_keywords import normalize_primary_keywords, parse_primary_keywords


class MePatchRequest(BaseModel):
    """Dashboard / settings: update site URL then run Maps scan."""

    business_url: str = Field(min_length=4, max_length=2048)
    primary_keyword: str | None = Field(default=None, max_length=1000)

    @field_validator("business_url")
    @classmethod
    def strip_url(cls, v: str) -> str:
        return v.strip()

    @field_validator("primary_keyword")
    @classmethod
    def strip_kw(cls, v: str | None) -> str | None:
        if v is None:
            return None
        normalized = normalize_primary_keywords(v)
        if not normalized:
            return None
        if len(parse_primary_keywords(normalized)) > 12:
            raise ValueError("Maximum 12 primary keywords")
        return normalized
