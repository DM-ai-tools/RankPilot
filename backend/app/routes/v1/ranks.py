"""L4: Rank / suburb grid — L1 data in rp_rank_history + rp_suburb_grid."""

from fastapi import APIRouter, Depends

from app.deps import CurrentClientId, DbSession
from app.schemas.ranks import SuburbRanksResponse
from app.services.ranks_service import RanksService

router = APIRouter()


def get_ranks_service(session: DbSession) -> RanksService:
    return RanksService(session)


@router.get("/suburbs", response_model=SuburbRanksResponse)
async def list_suburb_ranks(
    client_id: CurrentClientId,
    svc: RanksService = Depends(get_ranks_service),
) -> SuburbRanksResponse:
    return await svc.list_suburbs(client_id)
