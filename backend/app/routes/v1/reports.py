"""L4: Monthly reports — rp_monthly_reports."""

from fastapi import APIRouter

from app.deps import CurrentClientId

router = APIRouter()


@router.get("/monthly")
async def list_monthly_reports(_client_id: CurrentClientId) -> dict:
    return {"items": []}
