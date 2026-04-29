"""All REST resources under /api/v1."""

from fastapi import APIRouter

from app.routes.v1 import (
    auth,
    chat,
    citations,
    content_queue,
    dashboard,
    gbp,
    health,
    integrations,
    jobs,
    me,
    opportunities,
    ranks,
    reports,
    reviews,
    scans,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(me.router, tags=["account"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(ranks.router, prefix="/ranks", tags=["ranks"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["reviews"])
api_router.include_router(content_queue.router, prefix="/content-queue", tags=["content-queue"])
api_router.include_router(opportunities.router, prefix="/opportunities", tags=["opportunities"])
api_router.include_router(gbp.router, prefix="/gbp", tags=["gbp"])
api_router.include_router(citations.router, prefix="/citations", tags=["citations"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(scans.router, prefix="/scans", tags=["scans"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(integrations.router, tags=["integrations"])
