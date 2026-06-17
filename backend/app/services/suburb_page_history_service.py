"""Persist suburb landing page generate/publish history for Content Engine."""

from __future__ import annotations

import contextlib
import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

logger = logging.getLogger(__name__)


async def ensure_suburb_page_history_table(session: AsyncSession) -> None:
    await session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS rp_suburb_page_history (
              id                 uuid PRIMARY KEY,
              client_id          uuid NOT NULL REFERENCES rp_clients(client_id) ON DELETE CASCADE,
              status             text NOT NULL DEFAULT 'generated',
              keyword            text NOT NULL DEFAULT '',
              suburb             text NOT NULL DEFAULT '',
              slug               text NOT NULL DEFAULT '',
              title              text NOT NULL DEFAULT '',
              excerpt            text NOT NULL DEFAULT '',
              content            text NOT NULL DEFAULT '',
              word_count         integer,
              image_photo_ids    jsonb NOT NULL DEFAULT '[]',
              module_set_used    jsonb NOT NULL DEFAULT '[]',
              modules_json       jsonb NOT NULL DEFAULT '[]',
              nearby_suburbs     text NOT NULL DEFAULT '',
              service_focus      text NOT NULL DEFAULT '',
              model              text,
              wordpress_page_id  integer,
              wordpress_link     text,
              generated_at       timestamptz NOT NULL DEFAULT now(),
              published_at       timestamptz,
              created_at         timestamptz NOT NULL DEFAULT now(),
              updated_at         timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    await session.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_suburb_page_history_client_time
              ON rp_suburb_page_history (client_id, created_at DESC)
            """
        )
    )
    await session.execute(
        text(
            """
            ALTER TABLE rp_suburb_page_history
              ADD COLUMN IF NOT EXISTS module_set_used jsonb NOT NULL DEFAULT '[]',
              ADD COLUMN IF NOT EXISTS modules_json jsonb NOT NULL DEFAULT '[]',
              ADD COLUMN IF NOT EXISTS nearby_suburbs text NOT NULL DEFAULT '',
              ADD COLUMN IF NOT EXISTS service_focus text NOT NULL DEFAULT ''
            """
        )
    )


def _parse_json_list(val: object) -> list:
    if isinstance(val, str):
        with contextlib.suppress(json.JSONDecodeError):
            val = json.loads(val)
    return list(val) if isinstance(val, list) else []


def _row_to_item(row: dict) -> dict:
    photo_ids = _parse_json_list(row.get("image_photo_ids"))
    module_set = _parse_json_list(row.get("module_set_used"))
    return {
        "id": str(row["id"]),
        "status": str(row.get("status") or ""),
        "keyword": str(row.get("keyword") or ""),
        "suburb": str(row.get("suburb") or ""),
        "slug": str(row.get("slug") or ""),
        "title": str(row.get("title") or ""),
        "excerpt": str(row.get("excerpt") or ""),
        "word_count": int(row["word_count"]) if row.get("word_count") is not None else None,
        "image_photo_ids": [str(x) for x in photo_ids if x],
        "module_set_used": [str(x) for x in module_set if x],
        "nearby_suburbs": str(row.get("nearby_suburbs") or ""),
        "service_focus": str(row.get("service_focus") or ""),
        "model": str(row.get("model") or "") or None,
        "wordpress_page_id": int(row["wordpress_page_id"]) if row.get("wordpress_page_id") else None,
        "wordpress_link": str(row.get("wordpress_link") or "") or None,
        "generated_at": row["generated_at"].isoformat() if row.get("generated_at") else None,
        "published_at": row["published_at"].isoformat() if row.get("published_at") else None,
    }


async def list_history(session: AsyncSession, client_id: UUID, *, limit: int = 50) -> list[dict]:
    await ensure_suburb_page_history_table(session)
    rows = (
        await session.execute(
            text(
                """
                SELECT id, status, keyword, suburb, slug, title, excerpt, word_count,
                       image_photo_ids, module_set_used, nearby_suburbs, service_focus,
                       model, wordpress_page_id, wordpress_link,
                       generated_at, published_at
                FROM rp_suburb_page_history
                WHERE client_id = :cid
                ORDER BY COALESCE(published_at, generated_at, created_at) DESC
                LIMIT :lim
                """
            ),
            {"cid": str(client_id), "lim": max(1, min(limit, 100))},
        )
    ).mappings().all()
    return [_row_to_item(dict(r)) for r in rows]


def _row_to_detail(row: dict) -> dict:
    base = _row_to_item(row)
    content = str(row.get("content") or "")
    modules_json = _parse_json_list(row.get("modules_json"))
    if modules_json:
        from app.services.local_seo_page_service import modules_to_markdown, normalize_modules  # noqa: PLC0415

        modules_json = normalize_modules([m for m in modules_json if isinstance(m, dict)])
        md = modules_to_markdown(modules_json)
        if md.strip():
            content = md
    photo_ids = base.get("image_photo_ids") or []
    roles = ["hero", "service"]
    images = [
        {"role": roles[i] if i < len(roles) else f"image-{i + 1}", "photo_id": pid, "url": None, "preview_data_url": None, "note": None}
        for i, pid in enumerate(photo_ids)
    ]
    base.update(
        {
            "history_id": base["id"],
            "content": content,
            "target_keyword": base["keyword"],
            "word_count": int(base["word_count"]) if base.get("word_count") is not None else len(content.split()),
            "images": images,
            "modules": modules_json,
        }
    )
    return base


async def get_history_item(session: AsyncSession, client_id: UUID, history_id: str) -> dict:
    await ensure_suburb_page_history_table(session)
    row = (
        await session.execute(
            text(
                """
                SELECT id, status, keyword, suburb, slug, title, excerpt, content, word_count,
                       image_photo_ids, module_set_used, modules_json, nearby_suburbs, service_focus,
                       model, wordpress_page_id, wordpress_link,
                       generated_at, published_at
                FROM rp_suburb_page_history
                WHERE id = :id AND client_id = :cid
                """
            ),
            {"id": history_id, "cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="History item not found.")
    return _row_to_detail(dict(row))


async def get_recent_suburb_image_photo_ids(
    session: AsyncSession,
    client_id: UUID,
    *,
    limit: int = 16,
) -> list[str]:
    """Collect photo IDs from recent suburb landing pages for image variety."""
    await ensure_suburb_page_history_table(session)
    rows = (
        await session.execute(
            text(
                """
                SELECT image_photo_ids
                FROM rp_suburb_page_history
                WHERE client_id = :cid
                ORDER BY COALESCE(published_at, generated_at, created_at) DESC
                LIMIT :lim
                """
            ),
            {"cid": str(client_id), "lim": max(1, min(limit, 30))},
        )
    ).scalars().all()
    seen: set[str] = set()
    out: list[str] = []
    for raw in rows:
        for pid in _parse_json_list(raw):
            s = str(pid).strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    return out


async def list_recent_module_sets(session: AsyncSession, client_id: UUID, *, limit: int = 5) -> list[list[str]]:
    await ensure_suburb_page_history_table(session)
    rows = (
        await session.execute(
            text(
                """
                SELECT module_set_used
                FROM rp_suburb_page_history
                WHERE client_id = :cid
                  AND module_set_used IS NOT NULL
                  AND module_set_used::text <> '[]'
                ORDER BY COALESCE(published_at, generated_at, created_at) DESC
                LIMIT :lim
                """
            ),
            {"cid": str(client_id), "lim": max(1, min(limit, 10))},
        )
    ).scalars().all()
    out: list[list[str]] = []
    for raw in rows:
        parsed = _parse_json_list(raw)
        if parsed:
            out.append([str(x) for x in parsed])
    return out


async def save_generated(
    session: AsyncSession,
    client_id: UUID,
    *,
    keyword: str,
    suburb: str,
    slug: str,
    title: str,
    excerpt: str,
    content: str,
    word_count: int,
    image_photo_ids: list[str],
    model: str,
    module_set_used: list[str] | None = None,
    modules_json: list[dict] | None = None,
    nearby_suburbs: str = "",
    service_focus: str = "",
) -> str:
    await ensure_suburb_page_history_table(session)
    item_id = str(uuid7())
    now = datetime.now(UTC)
    await session.execute(
        text(
            """
            INSERT INTO rp_suburb_page_history
                (id, client_id, status, keyword, suburb, slug, title, excerpt, content,
                 word_count, image_photo_ids, module_set_used, modules_json,
                 nearby_suburbs, service_focus, model, generated_at, created_at, updated_at)
            VALUES
                (:id, :cid, 'generated', :kw, :suburb, :slug, :title, :excerpt, :content,
                 :wc, CAST(:photos AS jsonb), CAST(:modset AS jsonb), CAST(:mods AS jsonb),
                 :nearby, :focus, :model, :now, :now, :now)
            """
        ),
        {
            "id": item_id,
            "cid": str(client_id),
            "kw": keyword,
            "suburb": suburb,
            "slug": slug,
            "title": title,
            "excerpt": excerpt,
            "content": content,
            "wc": word_count,
            "photos": json.dumps(image_photo_ids),
            "modset": json.dumps(module_set_used or []),
            "mods": json.dumps(modules_json or []),
            "nearby": nearby_suburbs,
            "focus": service_focus,
            "model": model,
            "now": now,
        },
    )
    await session.commit()
    return item_id


async def mark_published(
    session: AsyncSession,
    client_id: UUID,
    history_id: str | None,
    *,
    keyword: str,
    suburb: str,
    slug: str,
    title: str,
    excerpt: str,
    content: str,
    word_count: int | None,
    image_photo_ids: list[str],
    model: str | None,
    wordpress_page_id: int | None,
    wordpress_link: str,
) -> str:
    await ensure_suburb_page_history_table(session)
    now = datetime.now(UTC)
    if history_id:
        result = await session.execute(
            text(
                """
                UPDATE rp_suburb_page_history
                SET status = 'published',
                    slug = :slug,
                    title = :title,
                    excerpt = :excerpt,
                    content = :content,
                    word_count = COALESCE(:wc, word_count),
                    image_photo_ids = CAST(:photos AS jsonb),
                    wordpress_page_id = :wp_id,
                    wordpress_link = :wp_link,
                    published_at = :now,
                    updated_at = :now
                WHERE id = :id AND client_id = :cid
                RETURNING id
                """
            ),
            {
                "id": history_id,
                "cid": str(client_id),
                "slug": slug,
                "title": title,
                "excerpt": excerpt,
                "content": content,
                "wc": word_count,
                "photos": json.dumps(image_photo_ids),
                "wp_id": wordpress_page_id,
                "wp_link": wordpress_link,
                "now": now,
            },
        )
        row = result.mappings().first()
        if row:
            await session.commit()
            return str(row["id"])

    item_id = str(uuid7())
    await session.execute(
        text(
            """
            INSERT INTO rp_suburb_page_history
                (id, client_id, status, keyword, suburb, slug, title, excerpt, content,
                 word_count, image_photo_ids, model, wordpress_page_id, wordpress_link,
                 generated_at, published_at, created_at, updated_at)
            VALUES
                (:id, :cid, 'published', :kw, :suburb, :slug, :title, :excerpt, :content,
                 :wc, CAST(:photos AS jsonb), :model, :wp_id, :wp_link,
                 :now, :now, :now, :now)
            """
        ),
        {
            "id": item_id,
            "cid": str(client_id),
            "kw": keyword,
            "suburb": suburb,
            "slug": slug,
            "title": title,
            "excerpt": excerpt,
            "content": content,
            "wc": word_count,
            "photos": json.dumps(image_photo_ids),
            "model": model,
            "wp_id": wordpress_page_id,
            "wp_link": wordpress_link,
            "now": now,
        },
    )
    await session.commit()
    return item_id


async def delete_history_item(
    session: AsyncSession,
    client_id: UUID,
    history_id: str,
    *,
    delete_wordpress: bool = True,
) -> dict:
    await ensure_suburb_page_history_table(session)
    row = (
        await session.execute(
            text(
                """
                SELECT wordpress_page_id
                FROM rp_suburb_page_history
                WHERE id = :id AND client_id = :cid
                """
            ),
            {"id": history_id, "cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="History item not found.")

    wp_deleted = False
    wp_page_id = row.get("wordpress_page_id")
    if delete_wordpress and wp_page_id:
        from app.services.wordpress_publish_service import delete_wordpress_page  # noqa: PLC0415

        try:
            await delete_wordpress_page(session, client_id, int(wp_page_id))
            wp_deleted = True
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("WordPress page delete failed for history %s: %s", history_id, exc)

    await session.execute(
        text("DELETE FROM rp_suburb_page_history WHERE id = :id AND client_id = :cid"),
        {"id": history_id, "cid": str(client_id)},
    )
    await session.commit()
    return {"deleted": True, "wordpress_page_deleted": wp_deleted}
