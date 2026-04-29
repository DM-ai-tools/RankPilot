from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class JobStatusResponse(BaseModel):
    job_id: UUID
    job_type: str
    status: str
    payload: dict
    result: dict | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class ScanCreateRequest(BaseModel):
    keyword: str | None = None
    radius_km: int | None = None
