"""Publish approved content queue items (GBP + WordPress) on schedule."""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import session_maker
from app.services.gbp_service import publish_gbp_queue_description, publish_gbp_queue_post
from app.services.wordpress_publish_service import publish_landing_page_to_wordpress

logger = logging.getLogger(__name__)


async def publish_queue_item(session: AsyncSession, client_id: UUID, item_id: str) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT id, content_type, status, payload
                FROM rp_content_queue
                WHERE id = :id AND client_id = :cid
                """
            ),
            {"id": item_id, "cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        return {"ok": False, "error": "Item not found"}
    if str(row["status"]) not in ("approved", "published"):
        return {"ok": False, "error": f"Item status is {row['status']}, not approved"}

    ctype = str(row["content_type"])
    payload = row["payload"] if isinstance(row["payload"], dict) else {}
    if isinstance(row["payload"], str):
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            payload = {}

    if ctype == "gbp_post":
        result = await publish_gbp_queue_post(session, client_id, item_id)
        return {"ok": True, "type": ctype, **result}

    if ctype == "gbp_description":
        result = await publish_gbp_queue_description(session, client_id, item_id)
        return {"ok": True, "type": ctype, **result}

    if ctype == "landing_page":
        title = str(payload.get("title") or "Landing page")
        body = str(payload.get("body") or "")
        hint = str(payload.get("target_url") or "").strip() or None
        wp_link = await publish_landing_page_to_wordpress(
            session, client_id, title=title, body=body, target_url_hint=hint
        )
        await session.execute(
            text(
                """
                UPDATE rp_content_queue
                SET status = 'published',
                    published_at = now(),
                    target_url = COALESCE(:turl, target_url),
                    updated_at = now()
                WHERE id = :id AND client_id = :cid
                """
            ),
            {"id": item_id, "cid": str(client_id), "turl": wp_link},
        )
        return {"ok": True, "type": ctype, "target_url": wp_link}

    return {"ok": False, "error": f"Unsupported content type: {ctype}"}


async def publish_due_approved_content() -> None:
    """Publish approved items whose scheduled_for date is today or earlier."""
    today = date.today()
    maker = session_maker()
    async with maker() as session:
        await session.execute(text("SET LOCAL row_security = off"))
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id, client_id, content_type, payload
                    FROM rp_content_queue
                    WHERE status = 'approved'
                      AND content_type IN ('gbp_post', 'gbp_description', 'landing_page')
                      AND COALESCE(payload->>'scheduled_for', '') <> ''
                      AND (payload->>'scheduled_for')::date <= :today
                    ORDER BY (payload->>'scheduled_for')::date ASC
                    LIMIT 20
                    """
                ),
                {"today": today},
            )
        ).mappings().all()

    if not rows:
        return

    logger.info("content_publish: %d approved item(s) due for publish", len(rows))
    for row in rows:
        item_id = str(row["id"])
        client_id = UUID(str(row["client_id"]))
        async with maker() as session:
            await session.execute(text("SET LOCAL row_security = off"))
            try:
                result = await publish_queue_item(session, client_id, item_id)
                if result.get("ok"):
                    await session.commit()
                    logger.info("Published %s %s for client %s", row["content_type"], item_id, client_id)
                else:
                    await session.rollback()
                    logger.warning("Publish skipped %s: %s", item_id, result.get("error"))
            except Exception as exc:
                logger.exception("Failed to publish queue item %s: %s", item_id, exc)
                await session.rollback()
