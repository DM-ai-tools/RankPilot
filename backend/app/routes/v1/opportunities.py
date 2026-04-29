"""L4: Missed opportunities — derived from latest suburb ranks."""

from fastapi import APIRouter, Depends

from app.deps import CurrentClientId, DbSession
from app.schemas.opportunities import OpportunitiesResponse
from app.services.opportunities_service import OpportunitiesService

router = APIRouter()


def get_opportunities_service(session: DbSession) -> OpportunitiesService:
    return OpportunitiesService(session)


@router.get("/", response_model=OpportunitiesResponse)
async def list_opportunities(
    client_id: CurrentClientId,
    svc: OpportunitiesService = Depends(get_opportunities_service),
) -> OpportunitiesResponse:
    return await svc.list_opportunities(client_id)
