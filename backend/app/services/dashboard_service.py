"""L2: Dashboard scores — thin wrapper over overview aggregation."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.dashboard import DashboardScoresResponse
from app.services.overview_service import OverviewService


class DashboardService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_scores(self, client_id: UUID) -> DashboardScoresResponse:
        overview = await OverviewService().build(self._session, client_id)
        return DashboardScoresResponse(
            seo_visibility=overview.scores.seo_visibility,
            week_label=overview.week_label,
        )
