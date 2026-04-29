"""L4: Content queue — rp_content_queue."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.deps import CurrentClientId, DbSession
from app.schemas.content_queue import (
    ApproveAllResponse,
    ContentQueueItem,
    ContentQueueListResponse,
    StatusUpdateRequest,
)
from app.services.content_generation_service import generate_content_for_client
from app.services.content_queue_service import ContentQueueService

router = APIRouter()


def get_svc(session: DbSession) -> ContentQueueService:
    return ContentQueueService(session)


@router.get("/", response_model=ContentQueueListResponse)
async def list_queue(
    client_id: CurrentClientId,
    svc: ContentQueueService = Depends(get_svc),
) -> ContentQueueListResponse:
    return await svc.list_items(client_id)


@router.post("/purge-shell-items")
async def purge_shell_queue_items(
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    """Remove title-only rows (no `payload.body`) left from old demo seeds."""
    result = await session.execute(
        text(
            """
            DELETE FROM rp_content_queue
            WHERE client_id = :cid
              AND trim(coalesce(payload->>'body', '')) = ''
            RETURNING id
            """
        ),
        {"cid": str(client_id)},
    )
    n = len(result.fetchall())
    return {"removed": n}


@router.post("/generate")
async def generate_content(
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    """Generates landing pages + GBP description via Claude for the logged-in client."""
    return await generate_content_for_client(session, client_id)


@router.post("/approve-all", response_model=ApproveAllResponse)
async def approve_all(
    client_id: CurrentClientId,
    svc: ContentQueueService = Depends(get_svc),
) -> ApproveAllResponse:
    return await svc.approve_all(client_id)


@router.patch("/{item_id}/status", response_model=ContentQueueItem)
async def update_status(
    item_id: UUID,
    body: StatusUpdateRequest,
    client_id: CurrentClientId,
    svc: ContentQueueService = Depends(get_svc),
) -> ContentQueueItem:
    return await svc.update_status(client_id, item_id, body.status)
