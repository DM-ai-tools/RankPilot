from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        return v.strip()


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
