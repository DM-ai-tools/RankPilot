"""Job status polling."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import CurrentClientId, DbSession
from app.schemas.jobs import JobStatusResponse
from app.services.jobs_service import JobsService

router = APIRouter()


def get_jobs_service(session: DbSession) -> JobsService:
    return JobsService(session)


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job(
    job_id: UUID,
    client_id: CurrentClientId,
    svc: JobsService = Depends(get_jobs_service),
) -> JobStatusResponse:
    row = await svc.get_job(client_id, job_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return row
