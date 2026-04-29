from pydantic import BaseModel, Field, field_validator


class MePatchRequest(BaseModel):
    """Dashboard / settings: update site URL then run Maps scan."""

    business_url: str = Field(min_length=4, max_length=2048)
    primary_keyword: str | None = Field(default=None, max_length=256)

    @field_validator("business_url")
    @classmethod
    def strip_url(cls, v: str) -> str:
        return v.strip()

    @field_validator("primary_keyword")
    @classmethod
    def strip_kw(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None
