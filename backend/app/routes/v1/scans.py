"""Enqueue L1 scan jobs (DataForSEO worker consumes rp_jobs)."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import CurrentClientId, DbSession
from app.schemas.common import JobAcceptedResponse
from app.schemas.jobs import ScanCreateRequest
from app.services.jobs_service import JobsService

router = APIRouter()


def get_jobs_service(session: DbSession) -> JobsService:
    return JobsService(session)


@router.post("/maps", status_code=status.HTTP_202_ACCEPTED, response_model=JobAcceptedResponse)
async def enqueue_maps_scan(
    body: ScanCreateRequest,
    client_id: CurrentClientId,
    svc: JobsService = Depends(get_jobs_service),
) -> JobAcceptedResponse:
    try:
        return await svc.enqueue_scan(client_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
