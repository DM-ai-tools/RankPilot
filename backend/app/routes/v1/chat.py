"""L4: Ask-Your-SEO — SSE streaming; L2 Claude + tools (implement SSE in follow-up)."""

from fastapi import APIRouter

from app.deps import CurrentClientId

router = APIRouter()


@router.get("/threads")
async def list_threads(_client_id: CurrentClientId) -> dict:
    return {"items": []}
