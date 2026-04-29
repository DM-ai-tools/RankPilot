from uuid import UUID

from pydantic import BaseModel, Field


class JobAcceptedResponse(BaseModel):
    """202 Accepted body for long-running work."""

    job_id: UUID = Field(description="Poll GET /jobs/{job_id} or subscribe via SSE.")
    status: str = Field(default="queued")
