"""L4: Dashboard API — delegates to L2 aggregation."""

from fastapi import APIRouter, Depends

from app.deps import CurrentClientId, DbSession
from app.schemas.dashboard import DashboardScoresResponse
from app.schemas.dashboard_overview import DashboardOverviewResponse
from app.services.dashboard_service import DashboardService
from app.services.overview_service import OverviewService

router = APIRouter()


def get_dashboard_service(session: DbSession) -> DashboardService:
    return DashboardService(session)


@router.get("/scores", response_model=DashboardScoresResponse)
async def get_dashboard_scores(
    client_id: CurrentClientId,
    svc: DashboardService = Depends(get_dashboard_service),
) -> DashboardScoresResponse:
    return await svc.get_scores(client_id)


@router.get("/overview", response_model=DashboardOverviewResponse)
async def get_dashboard_overview(
    client_id: CurrentClientId,
    session: DbSession,
) -> DashboardOverviewResponse:
    return await OverviewService().build(session, client_id)
