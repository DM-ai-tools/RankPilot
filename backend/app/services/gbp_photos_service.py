"""GBP photo library — upload files and generate via Runway (Nano Banana / Gemini image)."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import logging
import re
import time
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.core.config import Settings, get_settings
from app.services.content_generation_service import _get_client_profile
from app.services.gbp_brand_kit_service import apply_brand_kit_to_image
from app.services.gbp_image_prompt_service import build_runway_prompt_for_gbp_post, encode_prompt_meta
from app.services.runway_service import RunwayService

logger = logging.getLogger(__name__)

BI_BASE = "https://mybusinessbusinessinformation.googleapis.com/v1"
GBP_V4_BASE = "https://mybusiness.googleapis.com/v4"
GBP_UPLOAD_BASE = "https://mybusiness.googleapis.com/upload/v1/media"
GBP_ACCOUNTS_URL = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
_GBP_LOCATIONS_READ_MASK = "name"
_PUBLISH_URL_TTL_SEC = 900
_MIN_PHOTO_BYTES = 10_240

_SLOT_TO_GBP_CATEGORY: dict[str, str] = {
    "cover": "COVER",
    "exterior": "EXTERIOR",
    "interior": "INTERIOR",
    "at work": "AT_WORK",
    "team": "AT_WORK",
    "products": "ADDITIONAL",
    "storefront": "EXTERIOR",
    "service": "ADDITIONAL",
}

# Google GBP photo aspect ratios (width / height).
_CATEGORY_ASPECT: dict[str, float] = {
    "COVER": 16 / 9,
    "PROFILE": 1.0,
}
_ASPECT_TOLERANCE = 0.06

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_UPLOAD_ROOT = _BACKEND_ROOT / "uploads" / "gbp"
_MAX_UPLOAD_BYTES = 12 * 1024 * 1024
_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/jpg"}


def _client_dir(client_id: UUID) -> Path:
    d = _UPLOAD_ROOT / str(client_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _photo_public_path(photo_id: str) -> str:
    return f"/api/v1/gbp/photos/{photo_id}/file"


async def _ensure_photos_table(session: AsyncSession) -> None:
    await session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS rp_gbp_photos (
              id uuid PRIMARY KEY,
              client_id uuid NOT NULL REFERENCES rp_clients(client_id) ON DELETE CASCADE,
              source text NOT NULL,
              prompt text,
              storage_path text NOT NULL,
              runway_task_id text,
              slot_label text,
              status text NOT NULL DEFAULT 'ready',
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    await session.execute(
        text("ALTER TABLE rp_gbp_photos ADD COLUMN IF NOT EXISTS gbp_media_name text")
    )
    await session.execute(
        text("ALTER TABLE rp_gbp_photos ADD COLUMN IF NOT EXISTS published_at timestamptz")
    )
    await session.execute(
        text("ALTER TABLE rp_gbp_photos ADD COLUMN IF NOT EXISTS external_source_url text")
    )


def _public_api_base(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    explicit = (s.public_api_base_url or "").strip()
    if explicit:
        return explicit.rstrip("/")
    base = (s.google_redirect_base_url or "http://localhost:8000").strip().rstrip("/")
    callback = "/api/v1/integrations/google/callback"
    if base.endswith(callback):
        base = base[: -len(callback)].rstrip("/")
    return base


def _google_can_fetch_publish_url(settings: Settings | None = None) -> bool:
    """True when sourceUrl is on the public internet (not localhost)."""
    low = _public_api_base(settings).lower()
    return "localhost" not in low and "127.0.0.1" not in low


def _slot_category(slot_label: str | None) -> str:
    key = (slot_label or "").strip().lower()
    return _SLOT_TO_GBP_CATEGORY.get(key, "ADDITIONAL")


def _gbp_publish_cache_path(storage_path: Path) -> Path:
    return storage_path.parent / f"{storage_path.stem}_gbp_publish{storage_path.suffix}"


def _prepare_image_for_category(file_path: Path, category: str) -> Path:
    """Center-crop to Google's required aspect ratio (e.g. Cover = 16:9)."""
    target = _CATEGORY_ASPECT.get(category)
    if not target:
        return file_path
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed; cannot auto-crop for category %s", category)
        return file_path

    out = _gbp_publish_cache_path(file_path)
    try:
        with Image.open(file_path) as im:
            im = im.convert("RGB") if im.mode not in ("RGB", "L") else im
            w, h = im.size
            if h == 0:
                return file_path
            current = w / h
            if abs(current - target) <= _ASPECT_TOLERANCE:
                return file_path
            if current > target:
                new_w = max(1, int(h * target))
                left = (w - new_w) // 2
                box = (left, 0, left + new_w, h)
            else:
                new_h = max(1, int(w / target))
                top = (h - new_h) // 2
                box = (0, top, w, top + new_h)
            cropped = im.crop(box)
            ext = file_path.suffix.lower()
            if ext in (".jpg", ".jpeg"):
                cropped.save(out, format="JPEG", quality=92)
            elif ext == ".webp":
                cropped.save(out, format="WEBP", quality=90)
            else:
                cropped.save(out, format="PNG")
        return out if out.is_file() else file_path
    except Exception:
        logger.warning("Could not prepare image for %s", category, exc_info=True)
        return file_path


def _publish_signature(photo_id: str, client_id: str, exp: int, secret: str) -> str:
    msg = f"{photo_id}:{client_id}:{exp}".encode()
    digest = hmac.new(secret.encode(), msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _verify_publish_signature(photo_id: str, client_id: str, exp: int, sig: str, secret: str) -> bool:
    if exp < int(time.time()):
        return False
    expected = _publish_signature(photo_id, client_id, exp, secret)
    return hmac.compare_digest(expected, (sig or "").strip())


def build_photo_publish_source_url(photo_id: str, client_id: UUID, settings: Settings | None = None) -> str:
    s = settings or get_settings()
    exp = int(time.time()) + _PUBLISH_URL_TTL_SEC
    sig = _publish_signature(photo_id, str(client_id), exp, s.jwt_secret_key)
    base = _public_api_base(s)
    qs = f"cid={client_id}&exp={exp}&sig={sig}"
    return f"{base}/api/v1/gbp/photos/{photo_id}/publish-source?{qs}"


async def list_gbp_photos(session: AsyncSession, client_id: UUID) -> list[dict]:
    await _ensure_photos_table(session)
    rows = (
        await session.execute(
            text(
                """
                SELECT id, source, prompt, storage_path, runway_task_id, slot_label, status,
                       gbp_media_name, published_at, created_at
                FROM rp_gbp_photos
                WHERE client_id = :cid AND status IN ('ready', 'published')
                ORDER BY created_at DESC
                LIMIT 50
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().all()
    out: list[dict] = []
    for r in rows:
        pid = str(r["id"])
        out.append(
            {
                "id": pid,
                "source": r["source"],
                "prompt": r["prompt"],
                "runway_task_id": r["runway_task_id"],
                "slot_label": r["slot_label"],
                "status": r["status"],
                "gbp_media_name": r.get("gbp_media_name"),
                "published_at": r["published_at"].isoformat() if r.get("published_at") else None,
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "url": _photo_public_path(pid),
            }
        )
    return out


async def resolve_publish_source_file(
    session: AsyncSession,
    photo_id: str,
    client_id: str,
    exp: int,
    sig: str,
) -> Path:
    settings = get_settings()
    if not _verify_publish_signature(photo_id, client_id, exp, sig, settings.jwt_secret_key):
        raise HTTPException(status_code=403, detail="Invalid or expired publish link")
    await session.execute(
        text("SELECT set_config('app.client_id', :cid, true)"),
        {"cid": client_id},
    )
    await _ensure_photos_table(session)
    row = (
        await session.execute(
            text(
                """
                SELECT storage_path FROM rp_gbp_photos
                WHERE id = :id AND client_id = :cid
                  AND status IN ('ready', 'published')
                """
            ),
            {"id": photo_id, "cid": client_id},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")
    path = Path(str(row["storage_path"]))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Photo file missing on server")
    cached = _gbp_publish_cache_path(path)
    if cached.is_file():
        return cached
    return path


async def get_photo_file_path(session: AsyncSession, client_id: UUID, photo_id: str) -> Path:
    await _ensure_photos_table(session)
    row = (
        await session.execute(
            text(
                """
                SELECT storage_path FROM rp_gbp_photos
                WHERE id = :id AND client_id = :cid AND status IN ('ready', 'published')
                """
            ),
            {"id": photo_id, "cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")
    path = Path(str(row["storage_path"]))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Photo file missing on server")
    return path


async def upload_gbp_photo(
    session: AsyncSession,
    client_id: UUID,
    file: UploadFile,
    slot_label: str | None = None,
) -> dict:
    await _ensure_photos_table(session)
    ctype = (file.content_type or "").split(";")[0].strip().lower()
    if ctype not in _ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Upload JPEG, PNG, or WebP only")

    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Image must be under 12 MB")
    if len(data) < 100:
        raise HTTPException(status_code=400, detail="File is empty or too small")

    ext = ".jpg" if ctype in ("image/jpeg", "image/jpg") else ".png" if ctype == "image/png" else ".webp"
    photo_id = str(uuid7())
    dest = _client_dir(client_id) / f"{photo_id}{ext}"
    dest.write_bytes(data)

    await session.execute(
        text(
            """
            INSERT INTO rp_gbp_photos
                (id, client_id, source, prompt, storage_path, slot_label, status)
            VALUES
                (:id, :cid, 'upload', NULL, :path, :label, 'ready')
            """
        ),
        {
            "id": photo_id,
            "cid": str(client_id),
            "path": str(dest),
            "label": (slot_label or "").strip() or None,
        },
    )
    return {"id": photo_id, "source": "upload", "url": _photo_public_path(photo_id)}


async def generate_gbp_photo(
    session: AsyncSession,
    client_id: UUID,
    prompt: str,
    slot_label: str | None = None,
) -> dict:
    await _ensure_photos_table(session)
    profile = await _get_client_profile(session, client_id)
    from app.services.gbp_brand_kit_service import get_brand_kit

    brand = await get_brand_kit(session, client_id)
    bname = str(profile.get("business_name") or brand.get("brand_name") or "local business").strip()
    keyword = str(profile.get("primary_keyword") or "").strip()
    metro = str(profile.get("metro_label") or "").strip()

    user_prompt = (prompt or "").strip()
    if not user_prompt:
        raise HTTPException(status_code=400, detail="Enter a prompt to generate an image")

    runway_prompt, meta = await build_runway_prompt_for_gbp_post(
        session,
        str(client_id),
        keyword=keyword or user_prompt[:80],
        business_name=bname,
        metro=metro,
        theme=user_prompt,
        post_body=user_prompt,
        brand_config=brand,
        post_index=1,
    )

    runway = RunwayService()
    try:
        result = await runway.text_to_image(runway_prompt)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Runway generate failed")
        raise HTTPException(status_code=502, detail=f"Image generation failed: {exc!s}") from exc

    urls = result.get("output_urls") or []
    if not urls:
        raise HTTPException(status_code=502, detail="Runway returned no image URL")

    photo_id = str(uuid7())
    dest = _client_dir(client_id) / f"{photo_id}.png"

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        img = await http.get(urls[0])
        if not img.is_success:
            raise HTTPException(status_code=502, detail="Failed to download generated image from Runway")
        dest.write_bytes(img.content)

    await apply_brand_kit_to_image(
        session,
        client_id,
        dest,
        preferred_background=meta.get("logo_background"),
    )

    runway_url = str(urls[0]).strip()
    await session.execute(
        text(
            """
            INSERT INTO rp_gbp_photos
                (id, client_id, source, prompt, storage_path, runway_task_id, slot_label, status, external_source_url)
            VALUES
                (:id, :cid, 'runway', :prompt, :path, :task, :label, 'ready', :ext_url)
            """
        ),
        {
            "id": photo_id,
            "cid": str(client_id),
            "prompt": encode_prompt_meta(meta, runway_prompt),
            "path": str(dest),
            "task": result.get("task_id"),
            "label": (slot_label or "").strip() or None,
            "ext_url": runway_url or None,
        },
    )
    return {
        "id": photo_id,
        "source": "runway",
        "model": result.get("model"),
        "prompt": user_prompt,
        "url": _photo_public_path(photo_id),
    }


async def generate_post_image_from_content(
    session: AsyncSession,
    client_id: UUID,
    post_body: str,
    *,
    business_name: str = "",
    keyword: str = "",
    metro: str = "",
    theme: str = "",
    brand_config: dict | None = None,
    post_index: int = 1,
    post_total: int = 1,
    prior_archetypes: list[str] | None = None,
    search_volume: int | None = None,
    keyword_difficulty: int | None = None,
) -> dict | None:
    """Generate a Runway image for a GBP post; returns {photo_id, url, archetype} or None."""
    runway = RunwayService()
    if not runway.configured():
        return None

    await _ensure_photos_table(session)
    snippet = (post_body or "").strip()[:400]
    theme_hint = (theme or "").strip()[:3500]
    bname = (business_name or "local business").strip()
    kw = (keyword or "services").strip()
    area = (metro or "").strip()

    runway_prompt, meta = await build_runway_prompt_for_gbp_post(
        session,
        str(client_id),
        keyword=kw,
        business_name=bname,
        metro=area,
        theme=theme_hint,
        post_body=snippet,
        brand_config=brand_config,
        post_index=post_index,
        post_total=post_total,
        prior_archetypes=prior_archetypes,
        search_volume=search_volume,
        keyword_difficulty=keyword_difficulty,
    )

    try:
        result = await runway.text_to_image(runway_prompt)
    except Exception as exc:
        logger.warning("Post image generation skipped: %s", exc)
        return None

    urls = result.get("output_urls") or []
    if not urls:
        return None

    photo_id = str(uuid7())
    dest = _client_dir(client_id) / f"{photo_id}.png"
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
            img = await http.get(urls[0])
            if not img.is_success:
                return None
            dest.write_bytes(img.content)
    except Exception:
        logger.warning("Post image download failed", exc_info=True)
        return None

    await apply_brand_kit_to_image(
        session,
        client_id,
        dest,
        preferred_background=meta.get("logo_background"),
    )

    runway_url = str(urls[0]).strip()
    await session.execute(
        text(
            """
            INSERT INTO rp_gbp_photos
                (id, client_id, source, prompt, storage_path, runway_task_id, slot_label, status, external_source_url)
            VALUES
                (:id, :cid, 'gbp_post', :prompt, :path, :task, 'At work', 'ready', :ext_url)
            """
        ),
        {
            "id": photo_id,
            "cid": str(client_id),
            "prompt": encode_prompt_meta(meta, runway_prompt),
            "path": str(dest),
            "task": result.get("task_id"),
            "ext_url": runway_url or None,
        },
    )
    return {
        "photo_id": photo_id,
        "url": _photo_public_path(photo_id),
        "model": result.get("model"),
        "archetype": meta.get("archetype"),
        "keyword": kw,
    }


async def delete_gbp_photo(session: AsyncSession, client_id: UUID, photo_id: str) -> dict:
    await _ensure_photos_table(session)
    row = (
        await session.execute(
            text(
                """
                SELECT storage_path FROM rp_gbp_photos
                WHERE id = :id AND client_id = :cid
                """
            ),
            {"id": photo_id, "cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")
    path = Path(str(row["storage_path"]))
    await session.execute(
        text("DELETE FROM rp_gbp_photos WHERE id = :id AND client_id = :cid"),
        {"id": photo_id, "cid": str(client_id)},
    )
    if path.is_file():
        with contextlib.suppress(OSError):
            path.unlink()
    return {"deleted": photo_id}


def _mime_for_path(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".webp":
        return "image/webp"
    return "image/png"


async def _resolve_v4_media_parent(token: str, location_name: str) -> str:
    """Map BI location name (locations/123) to v4 parent accounts/X/locations/Y."""
    loc = (location_name or "").strip()
    if not loc.startswith("locations/"):
        raise HTTPException(status_code=400, detail="Invalid GBP location id on integration.")
    if loc.startswith("accounts/") and "/locations/" in loc:
        return loc

    async with httpx.AsyncClient(timeout=25.0) as http:
        headers = {"Authorization": f"Bearer {token}"}
        acc_resp = await http.get(GBP_ACCOUNTS_URL, headers=headers)
        if not acc_resp.is_success:
            msg = ""
            with contextlib.suppress(Exception):
                msg = str(acc_resp.json().get("error", {}).get("message") or "")
            raise HTTPException(
                status_code=acc_resp.status_code if acc_resp.status_code < 500 else 502,
                detail=f"Could not list GBP accounts: {msg or acc_resp.text[:200]}",
            )
        accounts = (acc_resp.json().get("accounts") or []) if isinstance(acc_resp.json(), dict) else []
        qs = urllib.parse.urlencode({"pageSize": 100, "readMask": _GBP_LOCATIONS_READ_MASK})
        for acc in accounts:
            acc_name = str(acc.get("name") or "").strip()
            if not acc_name:
                continue
            loc_resp = await http.get(
                f"{BI_BASE}/{acc_name}/locations?{qs}",
                headers=headers,
            )
            if not loc_resp.is_success:
                continue
            payload = loc_resp.json() if isinstance(loc_resp.json(), dict) else {}
            for item in payload.get("locations") or []:
                if str(item.get("name") or "").strip() == loc:
                    return f"{acc_name}/{loc}"
    raise HTTPException(
        status_code=400,
        detail="Could not resolve GBP account for this location. Reconnect GBP and re-select your location.",
    )


def _is_public_https_url(url: str) -> bool:
    u = (url or "").strip().lower()
    return u.startswith("https://") and "localhost" not in u and "127.0.0.1" not in u


def _tmpfiles_direct_url(page_url: str) -> str | None:
    """tmpfiles.org API returns a preview page; Google needs the /dl/ raw image URL."""
    m = re.match(r"^https://tmpfiles\.org/([^/]+)/(.+)$", (page_url or "").strip())
    if not m:
        return None
    return f"https://tmpfiles.org/dl/{m.group(1)}/{m.group(2)}"


async def _verify_public_image_url(http: httpx.AsyncClient, url: str) -> bool:
    try:
        head = await http.head(url, follow_redirects=True)
        if head.is_success:
            ctype = (head.headers.get("content-type") or "").lower()
            return ctype.startswith("image/")
    except Exception:
        pass
    return False


async def _upload_tmpfiles(http: httpx.AsyncClient, file_path: Path, data: bytes, mime: str) -> str | None:
    resp = await http.post(
        "https://tmpfiles.org/api/v1/upload",
        files={"file": (file_path.name, data, mime)},
        headers={"User-Agent": "RankPilot/1.0"},
    )
    if not resp.is_success:
        logger.warning("tmpfiles upload HTTP %s: %s", resp.status_code, resp.text[:200])
        return None
    payload = resp.json() if resp.content else {}
    page_url = str((payload.get("data") or {}).get("url") or "").strip()
    direct = _tmpfiles_direct_url(page_url)
    if direct and await _verify_public_image_url(http, direct):
        return direct
    return None


async def _upload_freeimage(
    http: httpx.AsyncClient, data: bytes, api_key: str
) -> str | None:
    if not api_key:
        return None
    resp = await http.post(
        "https://freeimage.host/api/1/upload",
        data={
            "key": api_key,
            "source": base64.b64encode(data).decode(),
            "format": "json",
        },
        headers={"User-Agent": "RankPilot/1.0"},
    )
    if not resp.is_success:
        logger.warning("freeimage upload HTTP %s", resp.status_code)
        return None
    payload = resp.json() if resp.content else {}
    image = payload.get("image") if isinstance(payload, dict) else {}
    url = str((image or {}).get("url") or (image or {}).get("display_url") or "").strip()
    if _is_public_https_url(url) and await _verify_public_image_url(http, url):
        return url
    return None


async def _upload_imgbb(http: httpx.AsyncClient, data: bytes, api_key: str) -> str | None:
    if not api_key:
        return None
    resp = await http.post(
        "https://api.imgbb.com/1/upload",
        data={"key": api_key, "image": base64.b64encode(data).decode()},
        headers={"User-Agent": "RankPilot/1.0"},
    )
    if not resp.is_success:
        logger.warning("imgbb upload HTTP %s", resp.status_code)
        return None
    payload = resp.json() if resp.content else {}
    url = str((payload.get("data") or {}).get("url") or "").strip()
    if _is_public_https_url(url) and await _verify_public_image_url(http, url):
        return url
    return None


async def _dev_public_url_for_local_file(file_path: Path) -> str:
    """Localhost dev: host file at a public HTTPS image URL so Google sourceUrl works."""
    settings = get_settings()
    mime = _mime_for_path(file_path)
    data = file_path.read_bytes()
    freeimage_key = (settings.freeimage_api_key or "").strip()
    imgbb_key = (settings.imgbb_api_key or "").strip()

    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as http:
        url = await _upload_tmpfiles(http, file_path, data, mime)
        if url:
            return url
        url = await _upload_freeimage(http, data, freeimage_key)
        if url:
            return url
        url = await _upload_imgbb(http, data, imgbb_key)
        if url:
            return url

    raise HTTPException(
        status_code=502,
        detail=(
            "Could not host your photo for Google on localhost. Add FREEIMAGE_API_KEY or IMGBB_API_KEY "
            "(free at freeimage.host / imgbb.com) to backend/.env, or set PUBLIC_API_BASE_URL to your "
            "public API URL (e.g. Railway + ngrok)."
        ),
    )


async def _publish_photo_bytes_to_google(
    token: str,
    v4_parent: str,
    file_path: Path,
    category: str,
) -> str:
    """Upload photo bytes via v4 startUpload → upload → create."""
    from app.routes.v1.integrations import _gbp_media_error_detail

    data = file_path.read_bytes()
    if len(data) < _MIN_PHOTO_BYTES:
        raise HTTPException(
            status_code=400,
            detail="Image is too small for Google (minimum 10 KB). Upload a larger photo.",
        )

    headers = {"Authorization": f"Bearer {token}"}
    start_url = f"{GBP_V4_BASE}/{v4_parent}/media:startUpload"
    async with httpx.AsyncClient(timeout=90.0) as http:
        start_resp = await http.post(start_url, headers=headers, json={})
        if not start_resp.is_success:
            msg = ""
            with contextlib.suppress(Exception):
                msg = str(start_resp.json().get("error", {}).get("message") or start_resp.json())
            raise HTTPException(
                status_code=start_resp.status_code if start_resp.status_code < 500 else 502,
                detail=_gbp_media_error_detail(msg or start_resp.text[:300], context="GBP photo upload start failed"),
            )
        start_data = start_resp.json() if isinstance(start_resp.json(), dict) else {}
        resource_name = str(start_data.get("resourceName") or "").strip()
        if not resource_name:
            raise HTTPException(status_code=502, detail="Google did not return an upload resource for the photo.")

        upload_path = resource_name.lstrip("/")
        upload_url = f"{GBP_UPLOAD_BASE}/{upload_path}"
        upload_resp = await http.post(
            upload_url,
            params={"upload_type": "media"},
            headers={**headers, "Content-Type": _mime_for_path(file_path)},
            content=data,
        )
        if not upload_resp.is_success:
            msg = ""
            with contextlib.suppress(Exception):
                msg = str(upload_resp.json().get("error", {}).get("message") or upload_resp.text[:300])
            raise HTTPException(
                status_code=upload_resp.status_code if upload_resp.status_code < 500 else 502,
                detail=_gbp_media_error_detail(msg, context="GBP photo byte upload failed"),
            )

        create_body = {
            "mediaFormat": "PHOTO",
            "locationAssociation": {"category": category},
            "dataRef": {"resourceName": resource_name},
        }
        create_resp = await http.post(
            f"{GBP_V4_BASE}/{v4_parent}/media",
            headers={**headers, "Content-Type": "application/json"},
            json=create_body,
        )
    if not create_resp.is_success:
        msg = ""
        with contextlib.suppress(Exception):
            msg = str(create_resp.json().get("error", {}).get("message") or create_resp.json())
        raise HTTPException(
            status_code=create_resp.status_code if create_resp.status_code < 500 else 502,
            detail=_gbp_media_error_detail(msg or create_resp.text[:300], context="GBP photo create failed"),
        )
    result = create_resp.json() if isinstance(create_resp.json(), dict) else {}
    return str(result.get("name") or "")


def _google_error_message(resp: httpx.Response) -> str:
    with contextlib.suppress(Exception):
        payload = resp.json()
        if isinstance(payload, dict):
            err = payload.get("error") or {}
            if isinstance(err, dict):
                details = err.get("details") or []
                for block in details:
                    if not isinstance(block, dict):
                        continue
                    for item in block.get("errorDetails") or []:
                        if isinstance(item, dict) and item.get("message"):
                            field = str(item.get("field") or "").strip()
                            prefix = f"{field}: " if field else ""
                            return prefix + str(item["message"])
                if err.get("message"):
                    return str(err["message"])
    text = (resp.text or "").strip()
    if "<!DOCTYPE html>" in text or "<html" in text.lower():
        if resp.status_code == 404:
            return f"Google API returned 404 (wrong endpoint or location). Status {resp.status_code}."
        return f"Google API returned HTML error page (status {resp.status_code})."
    return text[:400] if text else f"HTTP {resp.status_code}"


async def _publish_photo_via_source_url(
    token: str,
    v4_parent: str,
    source_url: str,
    category: str,
) -> str:
    """Create location media via Google My Business API v4 using a public sourceUrl."""
    from app.routes.v1.integrations import _gbp_media_error_detail

    body = {
        "mediaFormat": "PHOTO",
        "locationAssociation": {"category": category},
        "sourceUrl": source_url,
    }
    url = f"{GBP_V4_BASE}/{v4_parent}/media"
    async with httpx.AsyncClient(timeout=90.0) as http:
        resp = await http.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
        )
    if not resp.is_success:
        msg = _google_error_message(resp)
        hint = ""
        low = (msg + str(resp.text)).lower()
        if "aspect ratio" in low:
            hint = (
                " Cover photos must be 16:9 landscape. Re-publish (auto-crop runs on publish) "
                "or choose Exterior / At work instead of Cover."
            )
        elif "fetch" in low or "source" in low or "url" in low or "404" in low:
            hint = (
                " Google must fetch your image from PUBLIC_API_BASE_URL (ngrok). "
                "Confirm ngrok is still running on port 8000."
            )
        raise HTTPException(
            status_code=resp.status_code if resp.status_code < 500 else 502,
            detail=_gbp_media_error_detail(msg, context="GBP photo upload failed") + hint,
        )
    data = resp.json() if isinstance(resp.json(), dict) else {}
    return str(data.get("name") or "")


async def publish_gbp_photo(session: AsyncSession, client_id: UUID, photo_id: str) -> dict:
    """Upload library photo to Google Business Profile (direct byte upload, like description PATCH)."""
    await _ensure_photos_table(session)
    row = (
        await session.execute(
            text(
                """
                SELECT id, slot_label, status, gbp_media_name, storage_path, external_source_url
                FROM rp_gbp_photos
                WHERE id = :id AND client_id = :cid
                """
            ),
            {"id": photo_id, "cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")
    if str(row.get("status") or "") == "published" and row.get("gbp_media_name"):
        return {
            "id": photo_id,
            "status": "published",
            "note": "Already published to Google Business Profile.",
            "gbp_media_name": row.get("gbp_media_name"),
        }

    from app.services.gbp_service import _gbp_integration

    intg = await _gbp_integration(session, client_id)
    if not intg:
        raise HTTPException(status_code=400, detail="Connect GBP and select a location first.")

    file_path = Path(str(row.get("storage_path") or ""))
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Photo file missing on server")

    from app.routes.v1.integrations import _get_google_access_token

    token = await _get_google_access_token(session, client_id, "gbp")
    category = _slot_category(str(row.get("slot_label") or ""))
    publish_path = _prepare_image_for_category(file_path, category)
    aspect_note = ""
    if publish_path != file_path:
        aspect_note = " Image was auto-cropped for Google (Cover requires 16:9 landscape)."
    location_name = intg["location_name"]
    settings = get_settings()
    errors: list[str] = []
    media_name = ""
    ext_url = str(row.get("external_source_url") or "").strip()

    try:
        v4_parent = await _resolve_v4_media_parent(token, location_name)
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc.detail),
        ) from exc

    # 1) ngrok / PUBLIC_API_BASE_URL — signed URL on your backend (preferred for local dev).
    if _google_can_fetch_publish_url(settings):
        source_url = build_photo_publish_source_url(photo_id, client_id, settings)
        try:
            media_name = await _publish_photo_via_source_url(
                token, v4_parent, source_url, category
            )
        except HTTPException as exc:
            errors.append(str(exc.detail))
            logger.warning("GBP v4 media (PUBLIC_API_BASE_URL) failed: %s", exc.detail)

    # 1b) ngrok failed — try direct CDN URL (Google cannot use localhost/ngrok interstitial).
    if not media_name and _google_can_fetch_publish_url(settings) and errors:
        try:
            temp_url = await _dev_public_url_for_local_file(publish_path)
            media_name = await _publish_photo_via_source_url(
                token, v4_parent, temp_url, category
            )
        except HTTPException as exc:
            errors.append(str(exc.detail))
            logger.warning("GBP v4 media (CDN fallback) failed: %s", exc.detail)

    # 2) Runway public URL for AI-generated photos.
    if not media_name and _is_public_https_url(ext_url):
        try:
            media_name = await _publish_photo_via_source_url(
                token, v4_parent, ext_url, category
            )
        except HTTPException as exc:
            errors.append(str(exc.detail))
            logger.warning("GBP v4 media (Runway URL) failed: %s", exc.detail)

    # 3) Fallback: third-party temp host (only when PUBLIC_API_BASE_URL is not set).
    if not media_name and not _google_can_fetch_publish_url(settings):
        try:
            temp_url = await _dev_public_url_for_local_file(publish_path)
            media_name = await _publish_photo_via_source_url(
                token, v4_parent, temp_url, category
            )
        except HTTPException as exc:
            errors.append(str(exc.detail))
            logger.warning("GBP v4 media (dev temp URL) failed: %s", exc.detail)

    # 4) v4 byte upload (last resort; often INVALID_ARGUMENT on create).
    if not media_name:
        try:
            media_name = await _publish_photo_bytes_to_google(token, v4_parent, publish_path, category)
        except HTTPException as exc:
            errors.append(str(exc.detail))
            logger.warning("GBP v4 media (bytes) failed: %s", exc.detail)
        except Exception as exc:
            logger.exception("GBP photo publish failed")
            raise HTTPException(status_code=502, detail=f"Failed to publish photo: {exc!s}") from exc

    if not media_name:
        if not _google_can_fetch_publish_url(settings):
            hint = (
                " Set PUBLIC_API_BASE_URL in backend/.env to your ngrok https URL "
                "(run: ngrok http 8000), restart the backend, then Publish again."
            )
        else:
            hint = ""
        detail = "Photo publish failed." + hint + (
            (" " + " | ".join(errors[:3])) if errors else " Google rejected the photo upload."
        )
        raise HTTPException(status_code=400, detail=detail)

    now = datetime.now(UTC)
    await session.execute(
        text(
            """
            UPDATE rp_gbp_photos
            SET status = 'published',
                gbp_media_name = :media,
                published_at = :now
            WHERE id = :id AND client_id = :cid
            """
        ),
        {"id": photo_id, "cid": str(client_id), "media": media_name or None, "now": now},
    )
    return {
        "id": photo_id,
        "status": "published",
        "gbp_media_name": media_name,
        "category": category,
        "note": "Published to your Google Business Profile. It may take a few minutes to appear on Maps."
        + aspect_note,
    }
