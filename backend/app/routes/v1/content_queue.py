"""L4: Content queue — rp_content_queue."""

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import text

from app.deps import CurrentClientId, DbSession
from app.services.content_export_service import build_content_queue_xlsx, content_export_filename
from app.schemas.content_queue import (
    ApproveAllResponse,
    ContentQueueItem,
    ContentQueueListResponse,
    StatusUpdateRequest,
)
from app.services.content_generation_service import generate_content_for_client
from app.services.content_queue_service import ContentQueueService
from app.services.content_publish_service import publish_queue_item
from app.services.content_timeline_service import generate_monthly_timeline

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


@router.post("/generate-timeline")
async def generate_timeline(
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    """4-week GBP posts + landing pages from Ahrefs suburb keywords."""
    return await generate_monthly_timeline(session, client_id)


@router.get("/export")
async def export_content_plan(
    client_id: CurrentClientId,
    session: DbSession,
) -> Response:
    """Excel download of pending/approved timeline content + photo URLs (review before approval)."""
    data = await build_content_queue_xlsx(session, client_id)
    filename = content_export_filename()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{item_id}/publish")
async def publish_content_item(
    item_id: UUID,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    """Publish an approved item immediately (GBP or WordPress)."""
    return await publish_queue_item(session, client_id, str(item_id))


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
