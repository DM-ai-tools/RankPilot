"""Google Business Profile — overview, posts, descriptions, photos, brand kit."""

from __future__ import annotations

from datetime import date

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import get_settings
from app.deps import CurrentClientId, DbSession
from app.services.content_export_service import (
    build_gbp_posts_xlsx,
    gbp_posts_export_filename,
)
from app.services.gbp_brand_kit_service import (
    get_brand_kit,
    save_brand_kit,
    upload_brand_logo,
)
from app.services.gbp_photos_service import (
    _mime_for_path,
    delete_gbp_photo,
    generate_gbp_photo,
    get_photo_file_path,
    list_gbp_photos,
    publish_gbp_photo,
    resolve_publish_source_file,
    upload_gbp_photo,
)
from app.services.gbp_service import (
    delete_gbp_post,
    generate_gbp_description,
    generate_gbp_post_directions,
    generate_gbp_posts,
    get_gbp_overview,
    publish_gbp_queue_post,
    save_description_draft,
    schedule_all_pending_posts,
    sync_gbp_posts_with_google,
    update_description_status,
    update_gbp_description,
    update_gbp_post,
)

router = APIRouter()

_bearer = HTTPBearer(auto_error=False)


async def _client_id_or_token_param(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    token: str | None = None,
) -> UUID:
    """Auth dep that also accepts ?token=<jwt> for browser image requests."""
    from uuid import UUID as _UUID
    settings = get_settings()
    raw_token = (credentials.credentials if credentials else None) or token
    if not raw_token:
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = jwt.decode(raw_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        cid = payload.get("client_id") or payload.get("sub")
        if cid is None:
            from fastapi import HTTPException, status
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token claims")
        return _UUID(str(cid))
    except (JWTError, ValueError):
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Could not validate credentials") from None


TokenClientId = Annotated[UUID, Depends(_client_id_or_token_param)]


# ── Request models ─────────────────────────────────────────────────────────────

class GeneratePostsReq(BaseModel):
    count: int = 1
    prompt: str | None = None


class GeneratePostDirectionsReq(BaseModel):
    count: int = 1
    keywords: list[str] = []


class UpdatePostReq(BaseModel):
    status: str | None = None
    body: str | None = None
    scheduled_for: str | None = None


class ScheduleAllReq(BaseModel):
    mode: str = "daily"  # "daily" or "range"
    start_date: str | None = None
    end_date: str | None = None


class PublishPostReq(BaseModel):
    body: str | None = None


class GeneratePhotoReq(BaseModel):
    prompt: str
    slot_label: str | None = None


class SaveDescDraftReq(BaseModel):
    body: str


class UpdateDescReq(BaseModel):
    status: str | None = None
    body: str | None = None
    scheduled_for: str | None = None


class BrandKitReq(BaseModel):
    brand_name: str | None = None
    agency_type: str | None = None
    language: str = "English"
    brand_voice: str | None = None
    forbidden_words: str | None = None
    primary_color: str = "#FF5F32"
    secondary_color: str = "#000000"
    heading_font: str | None = None
    body_font: str | None = None


# ── Overview ──────────────────────────────────────────────────────────────────

@router.get("/overview")
async def gbp_overview(client_id: CurrentClientId, session: DbSession) -> dict:
    return await get_gbp_overview(session, client_id)


# ── Posts ─────────────────────────────────────────────────────────────────────

@router.post("/posts/generate")
async def api_generate_gbp_posts(
    req: GeneratePostsReq,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    return await generate_gbp_posts(session, client_id, count=req.count, prompts_raw=req.prompt)


@router.post("/posts/generate-directions")
async def api_generate_gbp_post_directions(
    req: GeneratePostDirectionsReq,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    return await generate_gbp_post_directions(
        session, client_id, count=req.count, keywords=req.keywords
    )


@router.post("/posts/schedule-all")
async def api_schedule_all_gbp_posts(
    req: ScheduleAllReq,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    return await schedule_all_pending_posts(
        session,
        client_id,
        mode=req.mode,
        start_date=req.start_date,
        end_date=req.end_date,
    )


@router.get("/posts/export")
async def api_export_gbp_posts(
    client_id: CurrentClientId,
    session: DbSession,
    post_ids: str | None = Query(None, description="Comma-separated post IDs to export"),
    date_from: str | None = Query(None, description="Include posts generated on/after (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="Include posts generated on/before (YYYY-MM-DD)"),
) -> Response:
    """Excel download of GBP posts — optionally filtered by date range and/or selected IDs."""
    parsed_ids = [p.strip() for p in (post_ids or "").split(",") if p.strip()]
    parsed_from: date | None = None
    parsed_to: date | None = None
    try:
        if date_from:
            parsed_from = date.fromisoformat(date_from.strip())
        if date_to:
            parsed_to = date.fromisoformat(date_to.strip())
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Invalid date format — use YYYY-MM-DD.") from exc

    if parsed_from and parsed_to and parsed_from > parsed_to:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="date_from must be on or before date_to.")

    data = await build_gbp_posts_xlsx(
        session,
        client_id,
        post_ids=parsed_ids or None,
        date_from=parsed_from,
        date_to=parsed_to,
    )
    filename = gbp_posts_export_filename(
        date_from=parsed_from,
        date_to=parsed_to,
        count=len(parsed_ids) if parsed_ids else None,
    )
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/posts/{post_id}")
async def api_update_gbp_post(
    post_id: str,
    req: UpdatePostReq,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    return await update_gbp_post(
        session, client_id, post_id, status=req.status, body=req.body, scheduled_for=req.scheduled_for
    )


@router.post("/posts/{post_id}/publish")
async def api_publish_gbp_post(
    post_id: str,
    req: PublishPostReq,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    return await publish_gbp_queue_post(
        session, client_id, post_id, post_body_override=req.body
    )


@router.delete("/posts/{post_id}")
async def api_delete_gbp_post(
    post_id: str,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    return await delete_gbp_post(session, client_id, post_id)


@router.post("/posts/sync")
async def api_sync_gbp_posts(client_id: CurrentClientId, session: DbSession) -> dict:
    return await sync_gbp_posts_with_google(session, client_id)


# ── Description ───────────────────────────────────────────────────────────────

class GenerateDescReq(BaseModel):
    user_keywords: list[str] = []


@router.post("/description/generate")
async def api_generate_gbp_description(
    req: GenerateDescReq,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    return await generate_gbp_description(session, client_id, user_keywords=req.user_keywords or None)


@router.post("/description/draft")
async def api_save_description_draft(
    req: SaveDescDraftReq,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    return await save_description_draft(session, client_id, req.body)


@router.patch("/description/{desc_id}")
async def api_update_gbp_description(
    desc_id: str,
    req: UpdateDescReq,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    return await update_gbp_description(
        session, client_id, desc_id, status=req.status, body=req.body, scheduled_for=req.scheduled_for
    )


@router.patch("/description/{desc_id}/status")
async def api_update_description_status(
    desc_id: str,
    new_status: str,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    return await update_description_status(session, client_id, desc_id, new_status)


# ── Photos ────────────────────────────────────────────────────────────────────

@router.get("/photos")
async def api_list_gbp_photos(client_id: CurrentClientId, session: DbSession) -> dict:
    photos = await list_gbp_photos(session, client_id)
    return {"photos": photos}


@router.get("/photos/{photo_id}/file")
async def api_get_photo_file(
    photo_id: str,
    client_id: TokenClientId,
    session: DbSession,
) -> FileResponse:
    """Serve photo file — supports ?token= for browser img tags."""
    path = await get_photo_file_path(session, client_id, photo_id)
    return FileResponse(str(path), media_type=_mime_for_path(path))


@router.get("/photos/{photo_id}/publish-source")
async def api_photo_publish_source(
    photo_id: str,
    cid: UUID = Query(..., description="Client id (signed URL)"),
    exp: int = Query(..., description="Expiry unix timestamp"),
    sig: str = Query(..., description="HMAC signature"),
) -> FileResponse:
    """Public signed URL — Google fetches post images (no JWT; HMAC verified)."""
    from app.db.session import session_maker

    async with session_maker()() as session:
        path = await resolve_publish_source_file(session, photo_id, str(cid), exp, sig)
    return FileResponse(
        str(path),
        media_type=_mime_for_path(path),
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.post("/photos/upload")
async def api_upload_gbp_photo(
    client_id: CurrentClientId,
    session: DbSession,
    file: UploadFile = File(...),
    slot_label: str | None = Form(default=None),
) -> dict:
    return await upload_gbp_photo(session, client_id, file, slot_label)


@router.post("/photos/generate")
async def api_generate_gbp_photo(
    req: GeneratePhotoReq,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    return await generate_gbp_photo(session, client_id, req.prompt, req.slot_label)


@router.delete("/photos/{photo_id}")
async def api_delete_gbp_photo(
    photo_id: str,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    return await delete_gbp_photo(session, client_id, photo_id)


@router.post("/photos/{photo_id}/publish")
async def api_publish_gbp_photo(
    photo_id: str,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    return await publish_gbp_photo(session, client_id, photo_id)


# ── Brand Kit ─────────────────────────────────────────────────────────────────

@router.get("/brand-kit")
async def api_get_brand_kit(client_id: CurrentClientId, session: DbSession) -> dict:
    return await get_brand_kit(session, client_id)


@router.post("/brand-kit")
async def api_save_brand_kit(
    req: BrandKitReq,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    return await save_brand_kit(
        session,
        client_id,
        brand_name=req.brand_name or "",
        agency_type=req.agency_type or "",
        language=req.language,
        brand_voice=req.brand_voice or "",
        forbidden_words=req.forbidden_words or "",
        primary_color=req.primary_color,
        secondary_color=req.secondary_color,
        heading_font=req.heading_font or "",
        body_font=req.body_font or "",
    )


@router.post("/brand-kit/logo")
async def api_upload_brand_logo(
    client_id: CurrentClientId,
    session: DbSession,
    file: UploadFile = File(...),
    variant: str = Form(default="light"),
) -> dict:
    kind = "on-light" if variant.strip().lower() in ("light", "on-light") else "on-dark"
    return await upload_brand_logo(session, client_id, kind, file)


@router.get("/brand-kit/logo/{kind}/file")
async def api_get_brand_logo_file(
    kind: str,
    client_id: TokenClientId,
) -> FileResponse:
    """Serve brand logo from disk — no DB session (DbSession requires Bearer header). Supports ?token=."""
    import pathlib

    from fastapi import HTTPException

    if kind not in ("on-dark", "on-light"):
        raise HTTPException(status_code=400, detail="Logo kind must be on-dark or on-light")
    prefix = f"logo_{kind.replace('-', '_')}"
    base = pathlib.Path("uploads/gbp/brandkit") / str(client_id)
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = base / f"{prefix}{ext}"
        if p.is_file():
            return FileResponse(str(p))
    raise HTTPException(status_code=404, detail="Logo file not found")


# ── Activity (legacy stub) ────────────────────────────────────────────────────

@router.get("/activity")
async def gbp_activity(_client_id: CurrentClientId) -> dict:
    return {"items": []}
