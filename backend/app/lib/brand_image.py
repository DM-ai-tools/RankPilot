"""Burn brand-kit logo onto generated GBP images."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

_LOGO_WIDTH_RATIO = 0.18
_LOGO_MIN_PX = 48
_LOGO_MAX_PX = 240
_PAD_RATIO = 0.035
_LUM_THRESHOLD = 132
_BRIGHT_PIXEL_LUM = 185
_BRIGHT_RATIO_LIGHT = 0.28

BackdropKind = Literal["dark", "light"] | None
BackgroundKind = Literal["light", "dark"]


def _average_luminance(region) -> float:
    stat = region.convert("L")
    hist = stat.histogram()
    total = sum(hist)
    if total == 0:
        return 128.0
    return sum(i * hist[i] for i in range(256)) / total


def _bright_pixel_ratio(region, threshold: int = _BRIGHT_PIXEL_LUM) -> float:
    stat = region.convert("L")
    pixels = list(stat.getdata())
    if not pixels:
        return 0.0
    return sum(1 for p in pixels if p >= threshold) / len(pixels)


def _is_light_background(region) -> bool:
    """True for white walls, bright windows, sky — never pick white logo here."""
    avg = _average_luminance(region)
    bright = _bright_pixel_ratio(region)
    return avg >= _LUM_THRESHOLD or bright >= _BRIGHT_RATIO_LIGHT


def _placement_region(image):
    """Top-left sample area — same zone where the logo is burned."""
    w, h = image.size
    pad = max(8, int(min(w, h) * 0.04))
    sample_w = max(48, int(w * 0.22))
    sample_h = max(40, int(h * 0.14))
    return image.crop((pad, pad, pad + sample_w, pad + sample_h)), pad


def _valid_path(path: str | None) -> Path | None:
    if not path:
        return None
    p = Path(path)
    return p if p.is_file() else None


def _pick_logo_path(
    image,
    *,
    logo_on_dark_path: str | None,
    logo_on_light_path: str | None,
    preferred_background: BackgroundKind | None = None,
) -> tuple[Path | None, BackdropKind]:
    """Return (logo file, optional contrast backdrop).

    logo_on_dark  = light/white mark for dark backgrounds
    logo_on_light = dark mark for light/white backgrounds

    Never falls back to the wrong variant without a backdrop pill.
    """
    on_dark = _valid_path(logo_on_dark_path)
    on_light = _valid_path(logo_on_light_path)

    if preferred_background == "light":
        if on_light:
            return on_light, None
        if on_dark:
            return on_dark, "dark"
        return None, None

    if preferred_background == "dark":
        if on_dark:
            return on_dark, None
        if on_light:
            return on_light, "light"
        return None, None

    region, _ = _placement_region(image)
    light_bg = _is_light_background(region)

    if light_bg:
        if on_light:
            return on_light, None
        if on_dark:
            return on_dark, "dark"
        return None, None

    if on_dark:
        return on_dark, None
    if on_light:
        return on_light, "light"
    return None, None


def _draw_backdrop(layer, x: int, y: int, logo_w: int, logo_h: int, kind: BackdropKind) -> None:
    if not kind:
        return
    from PIL import ImageDraw

    pad = max(6, int(min(logo_w, logo_h) * 0.12))
    fill = (15, 23, 42, 190) if kind == "dark" else (255, 255, 255, 215)
    box = (x - pad, y - pad, x + logo_w + pad, y + logo_h + pad)
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(box, radius=max(6, pad // 2), fill=fill)


def apply_brand_to_image_path(
    image_path: Path,
    *,
    logo_on_dark_path: str | None,
    logo_on_light_path: str | None,
    preferred_background: BackgroundKind | None = None,
) -> bool:
    """Overlay brand logo top-left with auto variant + contrast backdrop. Returns True if applied."""
    if not logo_on_dark_path and not logo_on_light_path:
        return False
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed; skipping brand logo overlay")
        return False

    try:
        with Image.open(image_path) as base:
            base = base.convert("RGBA")
            logo_path, backdrop = _pick_logo_path(
                base,
                logo_on_dark_path=logo_on_dark_path,
                logo_on_light_path=logo_on_light_path,
                preferred_background=preferred_background,
            )
            if not logo_path:
                return False

            with Image.open(logo_path) as logo_raw:
                logo = logo_raw.convert("RGBA")
                w, h = base.size
                _, pad = _placement_region(base)
                target_w = max(_LOGO_MIN_PX, min(_LOGO_MAX_PX, int(w * _LOGO_WIDTH_RATIO)))
                ratio = target_w / max(1, logo.width)
                target_h = max(1, int(logo.height * ratio))
                logo = logo.resize((target_w, target_h), Image.Resampling.LANCZOS)

                x = pad
                y = pad

                layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
                _draw_backdrop(layer, x, y, logo.width, logo.height, backdrop)
                layer.paste(logo, (x, y), logo)
                composed = Image.alpha_composite(base, layer)

                ext = image_path.suffix.lower()
                if ext in (".jpg", ".jpeg"):
                    composed.convert("RGB").save(image_path, format="JPEG", quality=92)
                elif ext == ".webp":
                    composed.convert("RGB").save(image_path, format="WEBP", quality=90)
                else:
                    composed.save(image_path, format="PNG")
        return True
    except Exception:
        logger.warning("Brand logo overlay failed for %s", image_path, exc_info=True)
        return False
