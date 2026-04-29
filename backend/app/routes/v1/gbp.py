"""L4: Google Business Profile activity feed — L3 writes via rp_actions / rp_gbp_actions."""

from fastapi import APIRouter

from app.deps import CurrentClientId

router = APIRouter()


@router.get("/activity")
async def gbp_activity(_client_id: CurrentClientId) -> dict:
    return {"items": []}
