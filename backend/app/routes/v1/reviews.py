"""Google Business reviews summary via DataForSEO (read-only, no GBP OAuth for listing)."""

from fastapi import APIRouter, Depends

from app.deps import CurrentClientId, DbSession
from app.schemas.reviews import CompetitorVelocityResponse, ReviewsSummaryResponse
from app.services.reviews_service import ReviewsService

router = APIRouter()


def get_reviews_service(session: DbSession) -> ReviewsService:
    return ReviewsService(session)


@router.get("/summary", response_model=ReviewsSummaryResponse)
async def get_reviews_summary(
    client_id: CurrentClientId,
    svc: ReviewsService = Depends(get_reviews_service),
) -> ReviewsSummaryResponse:
    return await svc.fetch_summary(client_id)


@router.get("/competitors", response_model=CompetitorVelocityResponse)
async def get_competitor_velocity(
    client_id: CurrentClientId,
    svc: ReviewsService = Depends(get_reviews_service),
) -> CompetitorVelocityResponse:
    """Return competitor review counts + estimated velocity from Maps scan snapshots."""
    return await svc.fetch_competitor_velocity(client_id)
