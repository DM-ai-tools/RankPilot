"""GBP brand kit — colours, logos, voice; burned onto AI-generated images."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.lib.brand_image import apply_brand_to_image_path
from app.services.content_generation_service import _get_client_profile

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_BRAND_ROOT = _BACKEND_ROOT / "uploads" / "gbp" / "brandkit"
_MAX_LOGO_BYTES = 4 * 1024 * 1024
_ALLOWED_LOGO_TYPES = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _brand_dir(client_id: UUID) -> Path:
    d = _BRAND_ROOT / str(client_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _normalize_hex(value: str | None, default: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return default
    if not raw.startswith("#"):
        raw = f"#{raw}"
    return raw.upper() if _HEX_COLOR.match(raw) else default


async def _ensure_brand_kit_table(session: AsyncSession) -> None:
    await session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS rp_gbp_brand_kit (
              client_id uuid PRIMARY KEY REFERENCES rp_clients(client_id) ON DELETE CASCADE,
              brand_name text NOT NULL DEFAULT '',
              agency_type text NOT NULL DEFAULT '',
              language text NOT NULL DEFAULT 'English',
              brand_voice text NOT NULL DEFAULT '',
              forbidden_words text NOT NULL DEFAULT '',
              primary_color text NOT NULL DEFAULT '#FF5F32',
              secondary_color text NOT NULL DEFAULT '#000000',
              heading_font text NOT NULL DEFAULT '',
              body_font text NOT NULL DEFAULT '',
              logo_on_dark_path text,
              logo_on_light_path text,
              updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )


def _logo_public_path(kind: str) -> str:
    return f"/api/v1/gbp/brand-kit/logo/{kind}/file"


def _row_to_dict(row: dict, *, include_paths: bool = False) -> dict:
    logo_dark = row.get("logo_on_dark_path")
    logo_light = row.get("logo_on_light_path")
    out = {
        "brand_name": str(row.get("brand_name") or ""),
        "agency_type": str(row.get("agency_type") or ""),
        "language": str(row.get("language") or "English"),
        "brand_voice": str(row.get("brand_voice") or ""),
        "forbidden_words": str(row.get("forbidden_words") or ""),
        "primary_color": str(row.get("primary_color") or "#FF5F32"),
        "secondary_color": str(row.get("secondary_color") or "#000000"),
        "heading_font": str(row.get("heading_font") or ""),
        "body_font": str(row.get("body_font") or ""),
        "has_logo_on_dark": bool(logo_dark and Path(str(logo_dark)).is_file()),
        "has_logo_on_light": bool(logo_light and Path(str(logo_light)).is_file()),
        "logo_on_dark_url": _logo_public_path("on-dark") if logo_dark else None,
        "logo_on_light_url": _logo_public_path("on-light") if logo_light else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }
    if include_paths:
        out["logo_on_dark_path"] = str(logo_dark) if logo_dark else None
        out["logo_on_light_path"] = str(logo_light) if logo_light else None
    return out


async def _default_brand_kit(session: AsyncSession, client_id: UUID) -> dict:
    profile = await _get_client_profile(session, client_id)
    return {
        "brand_name": str(profile.get("business_name") or ""),
        "agency_type": str(profile.get("primary_keyword") or ""),
        "language": "English",
        "brand_voice": "",
        "forbidden_words": "",
        "primary_color": "#FF5F32",
        "secondary_color": "#000000",
        "heading_font": "",
        "body_font": "",
        "has_logo_on_dark": False,
        "has_logo_on_light": False,
        "logo_on_dark_url": None,
        "logo_on_light_url": None,
        "updated_at": None,
    }


async def get_brand_kit(session: AsyncSession, client_id: UUID) -> dict:
    await _ensure_brand_kit_table(session)
    row = (
        await session.execute(
            text("SELECT * FROM rp_gbp_brand_kit WHERE client_id = :cid"),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        return await _default_brand_kit(session, client_id)
    return _row_to_dict(dict(row))


async def get_brand_kit_with_paths(session: AsyncSession, client_id: UUID) -> dict:
    await _ensure_brand_kit_table(session)
    row = (
        await session.execute(
            text("SELECT * FROM rp_gbp_brand_kit WHERE client_id = :cid"),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        default = await _default_brand_kit(session, client_id)
        default["logo_on_dark_path"] = None
        default["logo_on_light_path"] = None
        return default
    return _row_to_dict(dict(row), include_paths=True)


async def save_brand_kit(session: AsyncSession, client_id: UUID, payload: dict) -> dict:
    await _ensure_brand_kit_table(session)
    profile = await _get_client_profile(session, client_id)
    existing = (
        await session.execute(
            text("SELECT brand_name FROM rp_gbp_brand_kit WHERE client_id = :cid"),
            {"cid": str(client_id)},
        )
    ).mappings().first()

    brand_name = str(payload.get("brand_name") or "").strip()
    if not brand_name:
        brand_name = str(profile.get("business_name") or "")

    agency_type = str(payload.get("agency_type") or "").strip()
    if not agency_type:
        agency_type = str(profile.get("primary_keyword") or "")

    now = datetime.now(UTC)
    values = {
        "cid": str(client_id),
        "brand_name": brand_name[:120],
        "agency_type": agency_type[:120],
        "language": str(payload.get("language") or "English").strip()[:40] or "English",
        "brand_voice": str(payload.get("brand_voice") or "").strip()[:4000],
        "forbidden_words": str(payload.get("forbidden_words") or "").strip()[:500],
        "primary_color": _normalize_hex(payload.get("primary_color"), "#FF5F32"),
        "secondary_color": _normalize_hex(payload.get("secondary_color"), "#000000"),
        "heading_font": str(payload.get("heading_font") or "").strip()[:80],
        "body_font": str(payload.get("body_font") or "").strip()[:80],
        "now": now,
    }

    if existing:
        await session.execute(
            text(
                """
                UPDATE rp_gbp_brand_kit SET
                  brand_name = :brand_name,
                  agency_type = :agency_type,
                  language = :language,
                  brand_voice = :brand_voice,
                  forbidden_words = :forbidden_words,
                  primary_color = :primary_color,
                  secondary_color = :secondary_color,
                  heading_font = :heading_font,
                  body_font = :body_font,
                  updated_at = :now
                WHERE client_id = :cid
                """
            ),
            values,
        )
    else:
        await session.execute(
            text(
                """
                INSERT INTO rp_gbp_brand_kit
                  (client_id, brand_name, agency_type, language, brand_voice, forbidden_words,
                   primary_color, secondary_color, heading_font, body_font, updated_at)
                VALUES
                  (:cid, :brand_name, :agency_type, :language, :brand_voice, :forbidden_words,
                   :primary_color, :secondary_color, :heading_font, :body_font, :now)
                """
            ),
            values,
        )
    return await get_brand_kit(session, client_id)


async def upload_brand_logo(
    session: AsyncSession,
    client_id: UUID,
    kind: str,
    file: UploadFile,
) -> dict:
    """kind: on-dark (light logo for dark backgrounds) or on-light (dark logo for light backgrounds)."""
    if kind not in ("on-dark", "on-light"):
        raise HTTPException(status_code=400, detail="Logo kind must be on-dark or on-light")

    await _ensure_brand_kit_table(session)
    ctype = (file.content_type or "").split(";")[0].strip().lower()
    if ctype not in _ALLOWED_LOGO_TYPES:
        raise HTTPException(status_code=400, detail="Upload PNG, JPEG, WebP, or SVG only")

    data = await file.read()
    if len(data) > _MAX_LOGO_BYTES:
        raise HTTPException(status_code=400, detail="Logo must be under 4 MB")
    if len(data) < 50:
        raise HTTPException(status_code=400, detail="File is empty or too small")

    ext = ".png"
    if ctype in ("image/jpeg", "image/jpg"):
        ext = ".jpg"
    elif ctype == "image/webp":
        ext = ".webp"

    dest = _brand_dir(client_id) / f"logo_{kind.replace('-', '_')}{ext}"
    dest.write_bytes(data)

    col = "logo_on_dark_path" if kind == "on-dark" else "logo_on_light_path"
    now = datetime.now(UTC)
    exists = (
        await session.execute(
            text("SELECT client_id FROM rp_gbp_brand_kit WHERE client_id = :cid"),
            {"cid": str(client_id)},
        )
    ).first()
    if exists:
        await session.execute(
            text(f"UPDATE rp_gbp_brand_kit SET {col} = :path, updated_at = :now WHERE client_id = :cid"),
            {"path": str(dest), "now": now, "cid": str(client_id)},
        )
    else:
        profile = await _get_client_profile(session, client_id)
        await session.execute(
            text(
                f"""
                INSERT INTO rp_gbp_brand_kit
                  (client_id, brand_name, agency_type, {col}, updated_at)
                VALUES
                  (:cid, :name, :agency, :path, :now)
                """
            ),
            {
                "cid": str(client_id),
                "name": str(profile.get("business_name") or "")[:120],
                "agency": str(profile.get("primary_keyword") or "")[:120],
                "path": str(dest),
                "now": now,
            },
        )

    kit = await get_brand_kit(session, client_id)
    kit["note"] = "Logo saved — new AI images will include this mark automatically."
    return kit


async def get_brand_logo_path(session: AsyncSession, client_id: UUID, kind: str) -> Path:
    if kind not in ("on-dark", "on-light"):
        raise HTTPException(status_code=400, detail="Invalid logo kind")
    await _ensure_brand_kit_table(session)
    col = "logo_on_dark_path" if kind == "on-dark" else "logo_on_light_path"
    row = (
        await session.execute(
            text(f"SELECT {col} AS path FROM rp_gbp_brand_kit WHERE client_id = :cid"),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    if not row or not row.get("path"):
        raise HTTPException(status_code=404, detail="Logo not uploaded yet")
    path = Path(str(row["path"]))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Logo file missing on server")
    return path


async def apply_brand_kit_to_image(
    session: AsyncSession,
    client_id: UUID,
    image_path: Path,
    *,
    preferred_background: str | None = None,
) -> bool:
    kit = await get_brand_kit_with_paths(session, client_id)
    bg: BackgroundKind | None = None
    if preferred_background in ("light", "dark"):
        bg = preferred_background  # type: ignore[assignment]
    return apply_brand_to_image_path(
        image_path,
        logo_on_dark_path=kit.get("logo_on_dark_path"),
        logo_on_light_path=kit.get("logo_on_light_path"),
        preferred_background=bg,
    )
