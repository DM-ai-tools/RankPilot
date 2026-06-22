"""Persist suburb landing page generate/publish history for Content Engine."""

from __future__ import annotations

import contextlib
import json
import logging
from datetime import UTC, date, datetime, timedelta
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


async def register_wordpress_page_publish(
    session: AsyncSession,
    client_id: UUID,
    *,
    wordpress_page_id: int,
    slug: str,
    title: str,
    wordpress_link: str,
    content: str = "",
    keyword: str = "",
    excerpt: str = "",
) -> str:
    """Track Content Engine / live-edit WordPress publishes in suburb page history."""
    from app.services.keyword_tracker_service import _slug_to_search_keyword

    await ensure_suburb_page_history_table(session)
    slug = slug.strip()
    kw = (keyword or "").strip() or _slug_to_search_keyword(slug)
    title = (title or "").strip() or slug.replace("-", " ").title()
    now = datetime.now(UTC)
    wc = len([w for w in (content or "").split() if w]) if content else None

    existing = (
        await session.execute(
            text(
                """
                SELECT id
                FROM rp_suburb_page_history
                WHERE client_id = :cid
                  AND (
                    LOWER(TRIM(slug)) = LOWER(TRIM(:slug))
                    OR wordpress_page_id = :wp_id
                  )
                ORDER BY CASE WHEN status = 'published' THEN 0 ELSE 1 END, updated_at DESC
                LIMIT 1
                """
            ),
            {"cid": str(client_id), "slug": slug, "wp_id": wordpress_page_id},
        )
    ).mappings().first()

    if existing:
        hist_id = str(existing["id"])
        await session.execute(
            text(
                """
                UPDATE rp_suburb_page_history
                SET status = 'published',
                    keyword = CASE WHEN COALESCE(TRIM(keyword), '') = '' THEN :kw ELSE keyword END,
                    slug = :slug,
                    title = :title,
                    excerpt = COALESCE(NULLIF(:excerpt, ''), excerpt),
                    content = CASE WHEN COALESCE(TRIM(:content), '') = '' THEN content ELSE :content END,
                    word_count = COALESCE(:wc, word_count),
                    wordpress_page_id = :wp_id,
                    wordpress_link = :wp_link,
                    published_at = COALESCE(published_at, :now),
                    updated_at = :now
                WHERE id = :id AND client_id = :cid
                """
            ),
            {
                "id": hist_id,
                "cid": str(client_id),
                "kw": kw,
                "slug": slug,
                "title": title,
                "excerpt": excerpt,
                "content": content,
                "wc": wc,
                "wp_id": wordpress_page_id,
                "wp_link": wordpress_link,
                "now": now,
            },
        )
        await session.commit()
        return hist_id

    hist_id = str(uuid7())
    await session.execute(
        text(
            """
            INSERT INTO rp_suburb_page_history
                (id, client_id, status, keyword, suburb, slug, title, excerpt, content,
                 word_count, image_photo_ids, model, wordpress_page_id, wordpress_link,
                 generated_at, published_at, created_at, updated_at)
            VALUES
                (:id, :cid, 'published', :kw, '', :slug, :title, :excerpt, :content,
                 :wc, '[]'::jsonb, NULL, :wp_id, :wp_link,
                 :now, :now, :now, :now)
            """
        ),
        {
            "id": hist_id,
            "cid": str(client_id),
            "kw": kw,
            "slug": slug,
            "title": title,
            "excerpt": excerpt,
            "content": content,
            "wc": wc,
            "wp_id": wordpress_page_id,
            "wp_link": wordpress_link,
            "now": now,
        },
    )
    await session.commit()
    return hist_id


def _suburb_slug_prefixes(slugs: set[str]) -> set[str]:
    prefixes: set[str] = set()
    for slug in slugs:
        parts = [p for p in slug.split("-") if p]
        if len(parts) >= 2:
            prefixes.add(f"{parts[0]}-{parts[1]}")
    return prefixes


def _matches_suburb_slug_family(slug: str, prefixes: set[str]) -> bool:
    s = slug.strip().lower()
    if not s or not prefixes:
        return False
    return any(s == prefix or s.startswith(f"{prefix}-") for prefix in prefixes)


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


def _best_google_position(organic: int | None, maps: int | None) -> int | None:
    """Lower rank number is better — prefer organic when both exist."""
    if organic is not None and maps is not None:
        return min(organic, maps)
    return organic if organic is not None else maps


def _format_position(organic: int | None, maps: int | None) -> str:
    pos = _best_google_position(organic, maps)
    if pos is None:
        return "Not in top 20"
    parts: list[str] = [f"#{pos}"]
    if organic is not None and maps is not None and organic != maps:
        parts.append(f"(organic #{organic}, Maps #{maps})")
    elif organic is not None and maps is None:
        parts.append("(organic)")
    elif maps is not None and organic is None:
        parts.append("(Maps)")
    return " ".join(parts)


async def _snapshot_weekly_pair(
    session: AsyncSession, client_id: UUID, keywords: list[str]
) -> tuple[dict[str, int | None], dict[str, int | None] | None]:
    kws = list({k.strip().lower() for k in keywords if (k or "").strip()})
    if not kws:
        return {"organic_position": None, "maps_position": None}, None

    rows = (
        await session.execute(
            text(
                """
                SELECT
                  DATE_TRUNC('week', checked_at)::date AS week,
                  MIN(organic_position) AS organic_position,
                  MIN(maps_position) AS maps_position
                FROM rp_keyword_rank_snapshot
                WHERE client_id = :cid
                  AND LOWER(TRIM(keyword)) = ANY(:kws)
                GROUP BY DATE_TRUNC('week', checked_at)
                ORDER BY week DESC
                LIMIT 2
                """
            ),
            {"cid": str(client_id), "kws": kws},
        )
    ).mappings().all()

    this_week = {
        "organic_position": rows[0]["organic_position"] if rows else None,
        "maps_position": rows[0]["maps_position"] if rows else None,
    }
    last_week = (
        {
            "organic_position": rows[1]["organic_position"],
            "maps_position": rows[1]["maps_position"],
        }
        if len(rows) > 1
        else None
    )
    return this_week, last_week


async def _gsc_weekly_pair(
    session: AsyncSession,
    client_id: UUID,
    *,
    keyword: str,
    page_url: str | None,
    slug: str,
) -> tuple[dict[str, int | None] | None, dict[str, int | None] | None]:
    from app.services.gsc_service import fetch_gsc_keyword_position
    from app.services.keyword_tracker_service import _search_keyword_candidates

    today = date.today()
    this_organic: int | None = None
    last_organic: int | None = None
    for kw in _search_keyword_candidates(keyword, slug):
        this = await fetch_gsc_keyword_position(
            session,
            client_id,
            keyword=kw,
            page_url=page_url,
            start_date=today - timedelta(days=6),
            end_date=today,
        )
        if this and this.get("organic_position"):
            pos = int(this["organic_position"])
            this_organic = pos if this_organic is None else min(this_organic, pos)
        prev = await fetch_gsc_keyword_position(
            session,
            client_id,
            keyword=kw,
            page_url=page_url,
            start_date=today - timedelta(days=13),
            end_date=today - timedelta(days=7),
        )
        if prev and prev.get("organic_position"):
            pos = int(prev["organic_position"])
            last_organic = pos if last_organic is None else min(last_organic, pos)

    this_week = {"organic_position": this_organic, "maps_position": None} if this_organic else None
    last_week = {"organic_position": last_organic, "maps_position": None} if last_organic else None
    return this_week, last_week


def _merge_week(
    snap: dict[str, int | None],
    gsc: dict[str, int | None] | None,
) -> dict[str, int | None]:
    organic = snap.get("organic_position")
    maps = snap.get("maps_position")
    if gsc:
        gsc_org = gsc.get("organic_position")
        if gsc_org is not None:
            organic = gsc_org if organic is None else min(organic, gsc_org)
    return {"organic_position": organic, "maps_position": maps}


async def _build_ranking_item(
    session: AsyncSession,
    client_id: UUID,
    *,
    history_id: str,
    keyword: str,
    slug: str,
    title: str,
    suburb: str,
    page_url: str | None,
    published_at: datetime | None,
) -> dict:
    from app.services.keyword_tracker_service import _search_keyword_candidates

    search_keywords = _search_keyword_candidates(keyword, slug)
    snap_this, snap_last = await _snapshot_weekly_pair(session, client_id, search_keywords)
    gsc_this, gsc_last = await _gsc_weekly_pair(
        session, client_id, keyword=keyword, page_url=page_url, slug=slug
    )
    this_week = _merge_week(snap_this, gsc_this)
    if snap_last or gsc_last:
        last_week = _merge_week(
            snap_last or {"organic_position": None, "maps_position": None},
            gsc_last,
        )
    else:
        last_week = None

    this_pos = _best_google_position(
        this_week.get("organic_position"), this_week.get("maps_position")
    )
    last_pos = (
        _best_google_position(
            last_week.get("organic_position"), last_week.get("maps_position")
        )
        if last_week
        else None
    )
    change: int | None = None
    if this_pos is not None and last_pos is not None:
        change = last_pos - this_pos

    rank_note = None
    if this_pos is None:
        if len(search_keywords) > 1:
            rank_note = (
                f"Also checked page slug query: “{search_keywords[1]}”. "
                "Click Refresh rankings for a live Google check, or connect Search Console."
            )
        else:
            rank_note = (
                "Not in Ahrefs top 20 — click Refresh rankings for a live Google check, "
                "or connect Search Console."
            )

    page_title = title.strip() or slug.replace("-", " ").title()
    return {
        "history_id": history_id,
        "title": page_title,
        "keyword": keyword,
        "search_keywords": search_keywords,
        "suburb": suburb,
        "slug": slug,
        "page_url": page_url,
        "published_at": published_at.isoformat() if published_at else None,
        "last_week_organic": last_week.get("organic_position") if last_week else None,
        "last_week_maps": last_week.get("maps_position") if last_week else None,
        "last_week_position": last_pos,
        "last_week_label": (
            _format_position(
                last_week.get("organic_position") if last_week else None,
                last_week.get("maps_position") if last_week else None,
            )
            if last_week and last_pos is not None
            else "No data"
        ),
        "this_week_organic": this_week.get("organic_position"),
        "this_week_maps": this_week.get("maps_position"),
        "this_week_position": this_pos,
        "this_week_label": _format_position(
            this_week.get("organic_position"), this_week.get("maps_position")
        ),
        "position_change": change,
        "is_ranking": this_pos is not None,
        "status": "ranking" if this_pos is not None else "not_ranking",
        "rank_note": rank_note,
    }


async def _published_ranking_sources(
    session: AsyncSession, client_id: UUID, *, persist_backfill: bool = False
) -> list[dict]:
    """RankPilot-published pages: suburb history + matching WordPress suburb landing pages."""
    from app.services.keyword_tracker_service import _slug_to_search_keyword
    from app.services.wordpress_publish_service import (
        _fetch_published_wp_pages,
        is_rankpilot_wordpress_html,
    )

    rows = (
        await session.execute(
            text(
                """
                SELECT id, keyword, suburb, slug, title, wordpress_page_id, wordpress_link, published_at
                FROM rp_suburb_page_history
                WHERE client_id = :cid
                  AND (
                    status = 'published'
                    OR (
                      wordpress_page_id IS NOT NULL
                      AND COALESCE(TRIM(wordpress_link), '') <> ''
                    )
                  )
                  AND (
                    COALESCE(TRIM(keyword), '') <> ''
                    OR COALESCE(TRIM(slug), '') <> ''
                  )
                ORDER BY published_at DESC NULLS LAST, created_at DESC
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().all()

    sources: list[dict] = []
    known_slugs: set[str] = set()
    known_page_ids: set[int] = set()

    for row in rows:
        slug = str(row.get("slug") or "").strip()
        keyword = str(row["keyword"] or "").strip() or _slug_to_search_keyword(slug)
        wp_id = row.get("wordpress_page_id")
        if slug:
            known_slugs.add(slug.lower())
        if wp_id is not None:
            with contextlib.suppress(TypeError, ValueError):
                known_page_ids.add(int(wp_id))
        sources.append(
            {
                "history_id": str(row["id"]),
                "keyword": keyword,
                "slug": slug,
                "title": str(row.get("title") or "").strip(),
                "suburb": str(row.get("suburb") or "").strip(),
                "page_url": str(row.get("wordpress_link") or "").strip() or None,
                "published_at": row.get("published_at"),
            }
        )

    history_slug_rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT LOWER(TRIM(slug)) AS slug
                FROM rp_suburb_page_history
                WHERE client_id = :cid
                  AND COALESCE(TRIM(slug), '') <> ''
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().all()
    history_slugs = {str(r["slug"]) for r in history_slug_rows if r.get("slug")}
    slug_prefixes = _suburb_slug_prefixes(history_slugs)

    try:
        wp_pages = await _fetch_published_wp_pages(session, client_id)
    except Exception:
        logger.warning("WordPress pages unavailable for rankings", exc_info=True)
        wp_pages = []

    for page in wp_pages:
        slug = str(page.get("slug") or "").strip()
        if not slug:
            continue
        wp_id = int(page["id"])
        if slug.lower() in known_slugs or wp_id in known_page_ids:
            continue
        html = str(page.get("content_html") or "")
        if not is_rankpilot_wordpress_html(html) and not _matches_suburb_slug_family(slug, slug_prefixes):
            continue
        title = str(page.get("title") or "").strip()
        page_url = str(page.get("link") or "").strip() or None
        hist_id = f"rp-wp-{wp_id}"
        if persist_backfill:
            try:
                hist_id = await register_wordpress_page_publish(
                    session,
                    client_id,
                    wordpress_page_id=wp_id,
                    slug=slug,
                    title=title,
                    wordpress_link=page_url or "",
                )
            except Exception:
                logger.warning("Backfill suburb history failed for WP page %s", wp_id, exc_info=True)
        known_slugs.add(slug.lower())
        known_page_ids.add(wp_id)
        sources.append(
            {
                "history_id": hist_id,
                "keyword": _slug_to_search_keyword(slug),
                "slug": slug,
                "title": title,
                "suburb": "",
                "page_url": page_url,
                "published_at": None,
            }
        )
    return sources


async def get_published_suburb_page_rankings(session: AsyncSession, client_id: UUID) -> list[dict]:
    """Weekly Google rank comparison for published suburb landing page keywords."""
    await ensure_suburb_page_history_table(session)
    from app.services.keyword_tracker_service import _ensure_tracker_tables

    await _ensure_tracker_tables()

    sources = await _published_ranking_sources(session, client_id)
    out: list[dict] = []
    for src in sources:
        out.append(
            await _build_ranking_item(
                session,
                client_id,
                history_id=str(src["history_id"]),
                keyword=str(src["keyword"]),
                slug=str(src["slug"]),
                title=str(src["title"]),
                suburb=str(src.get("suburb") or ""),
                page_url=src.get("page_url"),
                published_at=src.get("published_at"),
            )
        )
    return out


async def sync_published_suburb_page_rankings(session: AsyncSession, client_id: UUID) -> dict:
    """Import published suburb keywords and refresh rank snapshots."""
    from app.services.keyword_tracker_service import check_suburb_page_rank, sync_tracked_keywords

    added = await sync_tracked_keywords(session, client_id)
    sources = await _published_ranking_sources(session, client_id, persist_backfill=True)

    checked = 0
    for src in sources:
        slug = str(src.get("slug") or "").strip()
        keyword = str(src.get("keyword") or "").strip()
        page_url = src.get("page_url")
        await check_suburb_page_rank(
            session,
            client_id,
            keyword=keyword,
            slug=slug,
            page_url=page_url,
            force=True,
        )
        checked += 1

    rankings = await get_published_suburb_page_rankings(session, client_id)
    return {
        "added_keywords": added,
        "checked": checked,
        "items": rankings,
    }

