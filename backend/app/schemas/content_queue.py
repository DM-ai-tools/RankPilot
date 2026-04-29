from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ContentQueueItem(BaseModel):
    id: UUID
    content_type: str
    title: str = Field(default="")
    status: str
    approval_mode: str
    word_count: int | None = None
    generated_at: datetime | None
    published_at: datetime | None
    target_url: str | None
    body: str | None = None
    notes: str | None = None


class ContentQueueListResponse(BaseModel):
    items: list[ContentQueueItem]


class StatusUpdateRequest(BaseModel):
    status: str = Field(pattern="^(pending|approved|published|rejected)$")


class ApproveAllResponse(BaseModel):
    updated: int
