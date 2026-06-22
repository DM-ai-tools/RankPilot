"""Publish RankPilot queue items to WordPress via REST (Application Password)."""

from __future__ import annotations

import contextlib
import html
import json
import logging
import re
from urllib.parse import urlparse
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Display constraints for images embedded in WordPress page HTML.
_WP_IMG_HERO_MAX_W = 1200
_WP_IMG_HERO_MAX_H = 675  # 16:9 at max width
_WP_IMG_INLINE_MAX_W = 960
_WP_IMG_INLINE_MAX_H = 540
_WP_UPLOAD_MAX_SIDE = 1280  # resize before upload (longest edge)


def _resize_image_bytes(data: bytes, *, max_side: int = _WP_UPLOAD_MAX_SIDE) -> tuple[bytes, str]:
    """Downscale large AI images before WordPress upload. Returns (bytes, extension)."""
    from io import BytesIO

    try:
        from PIL import Image
    except ImportError:
        return data, ".png"

    try:
        with Image.open(BytesIO(data)) as im:
            w, h = im.size
            if max(w, h) > max_side:
                scale = max_side / max(w, h)
                im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
            has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
            out = BytesIO()
            if has_alpha:
                im.save(out, format="PNG", optimize=True)
                return out.getvalue(), ".png"
            rgb = im.convert("RGB") if im.mode != "RGB" else im
            rgb.save(out, format="JPEG", quality=85, optimize=True)
            return out.getvalue(), ".jpg"
    except Exception:
        logger.warning("Image resize failed; uploading original bytes", exc_info=True)
        return data, ".png"


def _wp_figure_html(src: str, alt: str, *, layout: str = "hero") -> str:
    """Return a WordPress-safe <figure> — hero is full-width 16:9 landscape; inline is in-content wide."""
    safe_alt = html.escape(alt)
    safe_src = html.escape(src, quote=True)
    if layout == "inline":
        img_style = (
            "display:block;width:100%;max-width:100%;height:auto;"
            f"max-height:{_WP_IMG_INLINE_MAX_H}px;object-fit:cover;border-radius:8px;"
        )
        fig_style = "width:100%;max-width:100%;margin:1.5rem 0;"
    else:
        img_style = (
            "display:block;width:100%;max-width:100%;height:auto;"
            f"max-height:{_WP_IMG_HERO_MAX_H}px;object-fit:cover;border-radius:8px;"
        )
        fig_style = "width:100%;max-width:100%;margin:0 0 1.5rem 0;"
    return (
        f'<figure class="wp-block-image rankpilot-page-image rankpilot-page-image--{layout}" '
        f'style="{fig_style}">'
        f'<img src="{safe_src}" alt="{safe_alt}" loading="lazy" '
        f'style="{img_style}" /></figure>\n'
    )


_RANKPILOT_FIGURE_RE = re.compile(
    r'<figure[^>]*class="[^"]*rankpilot-page-image[^"]*"[^>]*>.*?</figure>',
    re.IGNORECASE | re.DOTALL,
)


def extract_rankpilot_figures(html_content: str) -> list[str]:
    """Return inline hero/service figures previously embedded by RankPilot."""
    return _RANKPILOT_FIGURE_RE.findall(html_content or "")


_RANKPILOT_PAGE_MARKERS = (
    "rankpilot-page-image",
    "rankpilot-faq-accordion",
    "rankpilot-page-content",
    "rankpilot-published",
    "<!--rankpilot",
)

RANKPILOT_PUBLISHED_HTML_MARKER = "<!-- rankpilot-published -->"


def is_rankpilot_wordpress_html(html: str) -> bool:
    """True when page body was generated or saved through RankPilot."""
    h = (html or "").lower()
    return any(marker in h for marker in _RANKPILOT_PAGE_MARKERS)


def embed_rankpilot_figures_in_body(body_html: str, figures: list[str]) -> str:
    """Prepend hero figure and insert a second figure mid-page when present."""
    if not figures:
        return body_html
    hero = figures[0]
    mid = figures[1] if len(figures) >= 2 else ""
    final_html = hero
    if mid:
        blocks = re.split(r"(</h2>)", body_html)
        if len(blocks) >= 5:
            insert_at = 3
            final_html += "".join(blocks[:insert_at]) + mid + "".join(blocks[insert_at:])
        else:
            final_html += body_html + mid
    else:
        final_html += body_html
    return final_html


def _slugify(title: str, max_len: int = 80) -> str:
    s = (title or "").lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[-\s]+", "-", s).strip("-")
    return (s[:max_len] if s else "landing-page") or "landing-page"


def _slug_from_target_hint(hint: str | None) -> str | None:
    if not hint or not isinstance(hint, str):
        return None
    raw = hint.strip().rstrip("/")
    if not raw:
        return None
    path = urlparse(raw).path.strip("/")
    if path:
        seg = path.split("/")[-1]
        if seg:
            return re.sub(r"[^\w-]", "", seg.lower())[:80] or None
    return None


def _normalize_site(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    if u and not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u


async def publish_landing_page_to_wordpress(
    session: AsyncSession,
    client_id: UUID,
    *,
    title: str,
    body: str,
    target_url_hint: str | None = None,
) -> str:
    """
    Create a published **Page** on the client's WordPress site (wp-admin → Pages).
    Returns the public permalink (``link`` from WP JSON).
    """
    row = (
        await session.execute(
            text(
                """
                SELECT access_token, extra_data
                FROM rp_integrations
                WHERE client_id = :cid AND type = 'wordpress'
                LIMIT 1
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WordPress is not connected. Add it from Onboarding (Connect WordPress) with an Application Password.",
        )

    app_password = str(row["access_token"] or "").strip()
    extra = row["extra_data"]
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except json.JSONDecodeError:
            extra = {}
    if not isinstance(extra, dict):
        extra = {}
    site = _normalize_site(str(extra.get("site_url") or ""))
    wp_user = str(extra.get("username") or "").strip()
    if not site or not wp_user or not app_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WordPress integration is incomplete. Re-connect WordPress from Onboarding.",
        )

    slug = _slug_from_target_hint(target_url_hint) or _slugify(title)
    html = (body or "").strip()
    if not html:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot publish an empty page body.")

    # If model returned plain text / markdown without HTML tags, wrap so WP renders predictably.
    if "<" not in html[:500]:
        import html as html_lib

        parts = [f"<p>{html_lib.escape(p.strip())}</p>" for p in re.split(r"\n\s*\n", html) if p.strip()]
        html = "\n".join(parts) if parts else f"<p>{html_lib.escape(html)}</p>"

    url = f"{site}/wp-json/wp/v2/pages"
    headers = {
        "User-Agent": "RankPilot/1.0 (WordPress page publish)",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload: dict = {"title": title, "content": html, "status": "publish", "slug": slug}

    async with httpx.AsyncClient(timeout=45, follow_redirects=True) as http:
        for attempt in range(3):
            r = await http.post(
                url,
                json=payload,
                auth=(wp_user, app_password),
                headers=headers,
            )
            if r.status_code in (200, 201):
                data = r.json()
                link = str(data.get("link") or "").strip()
                if not link:
                    link = f"{site}/?page_id={data.get('id', '')}"
                return link
            if r.status_code in (400, 409) and attempt < 2:
                payload["slug"] = f"{slug}-rankpilot-{attempt + 2}"
                continue
            detail = r.text[:400] if r.text else r.reason_phrase
            if r.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="WordPress rejected credentials when publishing. Re-create an Application Password and reconnect WordPress.",
                ) from None
            if r.status_code == 403:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="WordPress returned Forbidden when creating the page. Check the user can publish pages and REST is not blocked.",
                ) from None
            logger.warning("WordPress publish failed HTTP %s: %s", r.status_code, detail)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"WordPress publish failed ({r.status_code}): {detail}",
            ) from None


# ════════════════════════════════════════════════════════════════════════
# Suburb landing pages with images (Content Engine)
# ════════════════════════════════════════════════════════════════════════


async def _load_wp_credentials(session: AsyncSession, client_id: UUID) -> tuple[str, str, str]:
    """Return (site, username, app_password) for the client's WordPress integration."""
    row = (
        await session.execute(
            text(
                """
                SELECT access_token, extra_data
                FROM rp_integrations
                WHERE client_id = :cid AND type = 'wordpress'
                LIMIT 1
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WordPress is not connected. Add it from Business Setup (Connect WordPress).",
        )
    app_password = str(row["access_token"] or "").strip()
    extra = row["extra_data"]
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except json.JSONDecodeError:
            extra = {}
    if not isinstance(extra, dict):
        extra = {}
    site = _normalize_site(str(extra.get("site_url") or ""))
    wp_user = str(extra.get("username") or "").strip()
    if not site or not wp_user or not app_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WordPress integration is incomplete. Re-connect WordPress from Business Setup.",
        )
    return site, wp_user, app_password


def _imp(style: str) -> str:
    """Append !important to every declaration so theme CSS cannot override it."""
    parts = [p.strip() for p in style.split(";") if p.strip()]
    return ";".join(f"{p} !important" for p in parts)


# Font sizes are intentionally NOT forced — the WordPress theme's own typography
# (sizes/line-height) applies so pages match the rest of the live site. We only
# enforce alignment + case so theme overrides can't center/uppercase our copy.
_S_P = _imp("text-align:left;font-weight:400;margin:0 0 1rem 0;text-transform:none;letter-spacing:normal;color:inherit")
_S_H1 = _imp("text-align:left;text-transform:none;letter-spacing:normal")
_S_H2 = _imp("text-align:left;text-transform:none;letter-spacing:normal")
_S_H3 = _imp("text-align:left;text-transform:none;letter-spacing:normal")
_S_UL = _imp("text-align:left;margin:0 0 1rem 1.25rem;padding:0;list-style:disc;list-style-position:outside")
_S_OL = _imp("text-align:left;margin:0 0 1rem 1.25rem;padding:0;list-style:decimal;list-style-position:outside")
_S_LI = _imp("font-weight:400;margin-bottom:.35rem;text-align:left;text-transform:none;display:list-item")

_TAG_INLINE_STYLE: dict[str, str] = {
    "p": _S_P,
    "h1": _S_H1,
    "h2": _S_H2,
    "h3": _S_H3,
    "h4": _S_H3,
    "ul": _S_UL,
    "ol": _S_OL,
    "li": _S_LI,
}

_FAQ_SECTION_RE = re.compile(
    r'<section class="rankpilot-faq-accordion"[\s\S]*?</section>',
    re.IGNORECASE,
)


def _inject_inline_styles(html: str) -> str:
    """Add inline style= to every p/h1/h2/h3/ul/ol/li so WordPress can't override alignment."""
    def repl(m: re.Match[str]) -> str:
        tag = m.group(1).lower()
        attrs = m.group(2) or ""
        style = _TAG_INLINE_STYLE.get(tag, "")
        if not style:
            return m.group(0)
        attrs_clean = re.sub(r'\bstyle="[^"]*"', "", attrs).strip()
        return f"<{tag} style=\"{style}\"{' ' + attrs_clean if attrs_clean else ''}>"
    return re.sub(r"<(p|h[1-4]|ul|ol|li)((?:\s[^>]*)?)>", repl, html, flags=re.I)


def _wrap_page_body_html(html: str) -> str:
    """Inject inline styles on body elements; keep FAQ accordion untouched."""
    body = (html or "").strip()
    if not body:
        return body
    faq_match = _FAQ_SECTION_RE.search(body)
    if faq_match:
        faq_html = faq_match.group(0)
        main_html = (body[: faq_match.start()] + body[faq_match.end() :]).strip()
        if not main_html:
            return faq_html
        return _inject_inline_styles(main_html) + "\n\n" + faq_html
    if "rankpilot-page-content" in body[:300]:
        return body
    return _inject_inline_styles(body)


def _markdown_to_html(md: str) -> str:
    """Lightweight Markdown → HTML for WordPress page bodies.

    Handles headings (#..###), unordered lists (- / *), bold (**x**), and
    blank-line separated paragraphs. Preserves RankPilot FAQ accordion blocks.
    """
    import html as html_lib

    raw = (md or "").strip()
    if not raw:
        return ""

    from app.services.local_seo_page_service import faq_markdown_sections_to_accordion  # noqa: PLC0415

    raw = faq_markdown_sections_to_accordion(raw)

    faq_blocks: list[str] = []

    def _stash_faq(match: re.Match[str]) -> str:
        faq_blocks.append(match.group(1).strip())
        return f"\n\n<!--RP_FAQ_SLOT_{len(faq_blocks) - 1}-->\n\n"

    raw = re.sub(
        r"<!--RANKPILOT_FAQ-->\s*(.*?)\s*<!--/RANKPILOT_FAQ-->",
        _stash_faq,
        raw,
        flags=re.S,
    )

    if not faq_blocks and "<" in raw[:600] and re.search(
        r"<(p|h[1-6]|ul|ol|div|img|section)\b", raw[:600], re.I
    ):
        return raw  # already HTML (no mixed markdown)

    def _inline(text_in: str) -> str:
        esc = html_lib.escape(text_in.strip())
        esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        esc = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", esc)
        return esc

    lines = raw.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    list_buffer: list[str] = []
    list_ordered = False

    def _flush_list() -> None:
        nonlocal list_ordered
        if list_buffer:
            tag = "ol" if list_ordered else "ul"
            items = "".join(f"<li>{_inline(li)}</li>" for li in list_buffer)
            out.append(f"<{tag}>{items}</{tag}>")
            list_buffer.clear()
            list_ordered = False

    para_buffer: list[str] = []

    def _flush_para() -> None:
        if para_buffer:
            text_join = " ".join(p.strip() for p in para_buffer if p.strip())
            if text_join:
                out.append(f"<p>{_inline(text_join)}</p>")
            para_buffer.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            _flush_list()
            _flush_para()
            continue
        m_faq = re.match(r"^<!--RP_FAQ_SLOT_(\d+)-->$", stripped)
        if m_faq:
            _flush_list()
            _flush_para()
            out.append(stripped)
            continue
        m_h = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m_h:
            _flush_list()
            _flush_para()
            level = len(m_h.group(1))
            out.append(f"<h{level}>{_inline(m_h.group(2))}</h{level}>")
            continue
        m_li = re.match(r"^[-*]\s+(.*)$", stripped)
        if m_li:
            if list_buffer and list_ordered:
                _flush_list()
            _flush_para()
            list_ordered = False
            list_buffer.append(m_li.group(1))
            continue
        m_oli = re.match(r"^\d+\.\s+(.*)$", stripped)
        if m_oli:
            if list_buffer and not list_ordered:
                _flush_list()
            _flush_para()
            list_ordered = True
            list_buffer.append(m_oli.group(1))
            continue
        para_buffer.append(stripped)

    _flush_list()
    _flush_para()
    html_out = "\n".join(out)
    for i, block in enumerate(faq_blocks):
        slot = f"<!--RP_FAQ_SLOT_{i}-->"
        html_out = html_out.replace(f"<p>{slot}</p>", block)
        html_out = html_out.replace(slot, block)
    return _wrap_page_body_html(html_out)


async def _photo_bytes(
    session: AsyncSession, client_id: UUID, photo_id: str
) -> tuple[bytes, str] | None:
    """Resolve raw image bytes for a stored photo. Returns (bytes, extension)."""
    from app.services.gbp_photos_service import resolve_photo_file  # noqa: PLC0415

    try:
        path, alt = await resolve_photo_file(session, client_id, photo_id)
    except Exception:
        logger.warning("Could not resolve photo %s for WordPress upload", photo_id, exc_info=True)
        return None

    if path is not None:
        try:
            data = path.read_bytes()
            ext = path.suffix.lower() or ".png"
            return data, ext
        except Exception:
            return None
    if isinstance(alt, bytes):
        return alt, ".png"
    if isinstance(alt, str) and alt.startswith(("http://", "https://")):
        try:
            async with httpx.AsyncClient(timeout=45, follow_redirects=True) as http:
                r = await http.get(alt)
                if r.is_success and r.content:
                    ext = ".png"
                    ctype = r.headers.get("content-type", "")
                    if "jpeg" in ctype or "jpg" in ctype:
                        ext = ".jpg"
                    elif "webp" in ctype:
                        ext = ".webp"
                    return r.content, ext
        except Exception:
            return None
    return None


async def _upload_media_to_wordpress(
    http: httpx.AsyncClient,
    site: str,
    auth: tuple[str, str],
    *,
    data: bytes,
    filename: str,
    alt_text: str,
) -> tuple[int | None, str | None]:
    """Upload an image to the WP media library. Returns (media_id, source_url)."""
    ctype = "image/png"
    if filename.lower().endswith((".jpg", ".jpeg")):
        ctype = "image/jpeg"
    elif filename.lower().endswith(".webp"):
        ctype = "image/webp"
    headers = {
        "User-Agent": "RankPilot/1.0 (WordPress media upload)",
        "Accept": "application/json",
        "Content-Type": ctype,
        "Content-Disposition": f'attachment; filename="{filename}"',
    }
    try:
        r = await http.post(
            f"{site}/wp-json/wp/v2/media",
            content=data,
            auth=auth,
            headers=headers,
        )
    except httpx.HTTPError as exc:
        logger.warning("WordPress media upload request failed: %s", exc)
        return None, None
    if r.status_code not in (200, 201):
        logger.warning("WordPress media upload failed HTTP %s: %s", r.status_code, r.text[:200])
        return None, None
    payload = r.json()
    media_id = payload.get("id")
    source_url = str(payload.get("source_url") or "").strip() or None
    # Best-effort alt text update (non-fatal).
    if media_id and alt_text:
        with contextlib.suppress(Exception):
            await http.post(
                f"{site}/wp-json/wp/v2/media/{media_id}",
                json={"alt_text": alt_text[:120]},
                auth=auth,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
    return (int(media_id) if media_id is not None else None), source_url


async def publish_page_with_images(
    session: AsyncSession,
    client_id: UUID,
    *,
    title: str,
    content_markdown: str,
    excerpt: str | None = None,
    target_url_hint: str | None = None,
    image_photo_ids: list[str] | None = None,
) -> dict:
    """Create a published WordPress Page with generated content + inline images.

    The first image becomes the featured image and the page hero; a second
    image (if present) is inserted mid-content. Returns {link, slug, media_ids}.
    """
    site, wp_user, app_password = await _load_wp_credentials(session, client_id)
    auth = (wp_user, app_password)
    photo_ids = [p for p in (image_photo_ids or []) if p]

    body_html = _markdown_to_html(content_markdown)
    if not body_html.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot publish empty page content.")

    alt_base = (title or "").strip() or "Local service page"
    uploaded: list[tuple[int | None, str | None]] = []
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as http:
        for idx, pid in enumerate(photo_ids[:2]):
            resolved = await _photo_bytes(session, client_id, pid)
            if not resolved:
                continue
            data, ext = resolved
            data, ext = _resize_image_bytes(data)
            fname = f"{_slugify(alt_base)}-{idx + 1}{ext}"
            media_id, src_url = await _upload_media_to_wordpress(
                http, site, auth, data=data, filename=fname, alt_text=alt_base
            )
            if src_url:
                uploaded.append((media_id, src_url))

        figures: list[str] = []
        if len(uploaded) >= 1 and uploaded[0][1]:
            figures.append(_wp_figure_html(uploaded[0][1], alt_base, layout="hero"))
        if len(uploaded) >= 2 and uploaded[1][1]:
            figures.append(_wp_figure_html(uploaded[1][1], alt_base, layout="inline"))
        final_html = embed_rankpilot_figures_in_body(body_html, figures)
        if RANKPILOT_PUBLISHED_HTML_MARKER not in final_html:
            final_html = f"{final_html}\n{RANKPILOT_PUBLISHED_HTML_MARKER}"

        slug = _slug_from_target_hint(target_url_hint) or _slugify(title)
        payload: dict = {
            "title": title,
            "content": final_html,
            "status": "publish",
            "slug": slug,
        }
        if excerpt and excerpt.strip():
            payload["excerpt"] = excerpt.strip()
        # Intentionally omit featured_media — inline figures above are size-constrained.

        url = f"{site}/wp-json/wp/v2/pages"
        headers = {
            "User-Agent": "RankPilot/1.0 (WordPress page publish)",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        for attempt in range(3):
            r = await http.post(url, json=payload, auth=auth, headers=headers)
            if r.status_code in (200, 201):
                data_resp = r.json()
                link = str(data_resp.get("link") or "").strip()
                if not link:
                    link = f"{site}/?page_id={data_resp.get('id', '')}"
                return {
                    "link": link,
                    "slug": str(data_resp.get("slug") or slug),
                    "page_id": int(data_resp.get("id")) if data_resp.get("id") is not None else None,
                    "media_ids": [m for m, _ in uploaded if m],
                }
            if r.status_code in (400, 409) and attempt < 2:
                payload["slug"] = f"{slug}-rankpilot-{attempt + 2}"
                continue
            detail = r.text[:400] if r.text else r.reason_phrase
            if r.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="WordPress rejected credentials. Re-create an Application Password and reconnect WordPress.",
                ) from None
            if r.status_code == 403:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="WordPress returned Forbidden creating the page. Check the user can publish pages and REST is open.",
                ) from None
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"WordPress publish failed ({r.status_code}): {detail}",
            ) from None

    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="WordPress publish failed after retries.")


async def delete_wordpress_page(
    session: AsyncSession,
    client_id: UUID,
    page_id: int,
) -> None:
    """Permanently delete a WordPress page via REST API."""
    site, wp_user, app_password = await _load_wp_credentials(session, client_id)
    url = f"{site}/wp-json/wp/v2/pages/{int(page_id)}"
    params = {"force": "true"}
    headers = {
        "User-Agent": "RankPilot/1.0 (WordPress page delete)",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=45, follow_redirects=True) as http:
        r = await http.delete(url, params=params, auth=(wp_user, app_password), headers=headers)
    if r.status_code in (200, 410):
        return
    if r.status_code == 404:
        return  # already gone
    detail = r.text[:300] if r.text else r.reason_phrase
    if r.status_code == 401:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WordPress rejected credentials when deleting the page.",
        )
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"WordPress delete failed ({r.status_code}): {detail}",
    )


def _wp_page_summary_from_row(r: dict) -> dict[str, str | int] | None:
    if str(r.get("status") or "").strip().lower() not in ("publish", "published"):
        return None
    try:
        pid = int(r.get("id"))
    except (TypeError, ValueError):
        return None
    slug = str(r.get("slug") or "").strip()
    if not slug:
        return None
    title_field = r.get("title")
    if isinstance(title_field, dict):
        title = re.sub(
            r"<[^>]+>",
            "",
            str(title_field.get("rendered") or title_field.get("raw") or ""),
        ).strip()
    else:
        title = str(title_field or "").strip()
    content_field = r.get("content")
    rendered = ""
    if isinstance(content_field, dict):
        rendered = str(content_field.get("rendered") or "")
    elif isinstance(content_field, str):
        rendered = content_field
    return {
        "id": pid,
        "title": title or f"Page {pid}",
        "slug": slug,
        "link": str(r.get("link") or "").strip(),
        "content_html": rendered,
    }


async def _fetch_published_wp_pages(
    session: AsyncSession,
    client_id: UUID,
    *,
    per_page: int = 100,
) -> list[dict[str, str | int]]:
    import urllib.parse

    site, wp_user, app_password = await _load_wp_credentials(session, client_id)
    qs = urllib.parse.urlencode(
        {
            "per_page": max(1, min(per_page, 100)),
            "status": "publish",
            "orderby": "modified",
            "order": "desc",
            "_fields": "id,link,slug,title,status,content",
        }
    )
    url = f"{site}/wp-json/wp/v2/pages?{qs}"
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
        resp = await http.get(
            url,
            auth=(wp_user, app_password),
            headers={"Accept": "application/json", "User-Agent": "RankPilot/1.0 (WP pages)"},
        )
    if not resp.is_success:
        logger.warning("WordPress pages fetch failed (%s)", resp.status_code)
        return []
    payload = resp.json()
    rows = payload if isinstance(payload, list) else []
    out: list[dict[str, str | int]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        parsed = _wp_page_summary_from_row(r)
        if parsed:
            out.append(parsed)
    return out


async def list_rankpilot_wordpress_pages(
    session: AsyncSession,
    client_id: UUID,
    *,
    per_page: int = 100,
) -> list[dict[str, str | int]]:
    """Published WP pages whose HTML contains RankPilot markers (not all WP pages)."""
    pages = await _fetch_published_wp_pages(session, client_id, per_page=per_page)
    out: list[dict[str, str | int]] = []
    for page in pages:
        if is_rankpilot_wordpress_html(str(page.get("content_html") or "")):
            out.append({k: v for k, v in page.items() if k != "content_html"})
    return out


async def list_wordpress_pages_for_slugs(
    session: AsyncSession,
    client_id: UUID,
    slugs: set[str],
    *,
    per_page: int = 100,
) -> list[dict[str, str | int]]:
    """Published WP pages matching RankPilot suburb-history slugs only."""
    wanted = {s.strip().lower() for s in slugs if (s or "").strip()}
    if not wanted:
        return []
    pages = await _fetch_published_wp_pages(session, client_id, per_page=per_page)
    return [
        {k: v for k, v in page.items() if k != "content_html"}
        for page in pages
        if str(page.get("slug") or "").strip().lower() in wanted
    ]
