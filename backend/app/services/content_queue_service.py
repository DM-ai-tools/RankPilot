"""L3/L4: Content queue reads + status actions."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.content_queue import (
    ApproveAllResponse,
    ContentQueueItem,
    ContentQueueListResponse,
)
from app.services.wordpress_publish_service import publish_landing_page_to_wordpress


class ContentQueueService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_items(self, client_id: UUID) -> ContentQueueListResponse:
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT id, content_type, payload, status, approval_mode,
                           generated_at, published_at, target_url
                    FROM rp_content_queue
                    WHERE client_id = :cid
                    ORDER BY COALESCE(generated_at, created_at) DESC
                    LIMIT 100
                    """
                ),
                {"cid": str(client_id)},
            )
        ).mappings().all()

        items: list[ContentQueueItem] = []
        for r in rows:
            payload = r["payload"] or {}
            title = body = notes = ""
            wc = None
            if isinstance(payload, dict):
                title = str(payload.get("title") or "")
                body  = str(payload.get("body")  or "")
                notes = str(payload.get("notes") or "")
                w = payload.get("word_count")
                if w is not None:
                    wc = int(w)
            items.append(
                ContentQueueItem(
                    id=r["id"],
                    content_type=str(r["content_type"]),
                    title=title,
                    status=str(r["status"]),
                    approval_mode=str(r["approval_mode"]),
                    word_count=wc,
                    generated_at=r["generated_at"],
                    published_at=r["published_at"],
                    target_url=r["target_url"],
                    body=body or None,
                    notes=notes or None,
                )
            )
        return ContentQueueListResponse(items=items)

    async def update_status(self, client_id: UUID, item_id: UUID, new_status: str) -> ContentQueueItem:
        now = datetime.now(UTC)
        published_at = now if new_status == "published" else None

        wp_link: str | None = None
        if new_status == "published":
            cur = (
                await self._session.execute(
                    text(
                        """
                        SELECT content_type, payload
                        FROM rp_content_queue
                        WHERE id = :id AND client_id = :cid
                        """
                    ),
                    {"id": str(item_id), "cid": str(client_id)},
                )
            ).mappings().first()
            if not cur:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
            ctype = str(cur["content_type"] or "")
            payload = cur["payload"] or {}
            if not isinstance(payload, dict):
                payload = {}
            if ctype == "landing_page":
                title = str(payload.get("title") or "Landing page")
                body = str(payload.get("body") or "")
                hint = str(payload.get("target_url") or "").strip() or None
                wp_link = await publish_landing_page_to_wordpress(
                    self._session,
                    client_id,
                    title=title,
                    body=body,
                    target_url_hint=hint,
                )

        result = await self._session.execute(
            text(
                """
                UPDATE rp_content_queue
                SET status       = :status,
                    published_at = COALESCE(:pub, published_at),
                    target_url   = COALESCE(:turl, target_url),
                    updated_at   = now()
                WHERE id = :id AND client_id = :cid
                RETURNING id, content_type, payload, status, approval_mode,
                          generated_at, published_at, target_url
                """
            ),
            {
                "id":    str(item_id),
                "cid":   str(client_id),
                "status": new_status,
                "pub":   published_at,
                "turl":  wp_link,
            },
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
        payload = row["payload"] or {}
        title = body = notes = ""
        if isinstance(payload, dict):
            title = str(payload.get("title") or "")
            body = str(payload.get("body") or "")
            notes = str(payload.get("notes") or "")
        wc_raw = payload.get("word_count") if isinstance(payload, dict) else None
        return ContentQueueItem(
            id=row["id"],
            content_type=str(row["content_type"]),
            title=title,
            status=str(row["status"]),
            approval_mode=str(row["approval_mode"]),
            word_count=int(wc_raw) if wc_raw is not None else None,
            generated_at=row["generated_at"],
            published_at=row["published_at"],
            target_url=row["target_url"],
            body=body or None,
            notes=notes or None,
        )

    async def approve_all(self, client_id: UUID) -> ApproveAllResponse:
        result = await self._session.execute(
            text(
                """
                UPDATE rp_content_queue
                SET status = 'approved', updated_at = now()
                WHERE client_id = :cid AND status = 'pending'
                RETURNING id
                """
            ),
            {"cid": str(client_id)},
        )
        return ApproveAllResponse(updated=len(result.all()))
