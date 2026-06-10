from pathlib import Path

from PIL import Image

from app.lib.brand_image import (
    _is_light_background,
    _pick_logo_path,
    _placement_region,
    apply_brand_to_image_path,
)


def test_light_background_picks_dark_logo(tmp_path: Path):
    light_logo = tmp_path / "light.png"
    dark_logo = tmp_path / "dark.png"
    Image.new("RGBA", (120, 40), (255, 255, 255, 255)).save(light_logo)
    Image.new("RGBA", (120, 40), (0, 0, 0, 255)).save(dark_logo)

    bright = Image.new("RGB", (400, 300), (240, 245, 250))
    region, _ = _placement_region(bright)
    assert _is_light_background(region) is True

    picked, backdrop = _pick_logo_path(
        bright, logo_on_dark_path=str(light_logo), logo_on_light_path=str(dark_logo)
    )
    assert picked == Path(dark_logo)
    assert backdrop is None


def test_light_background_only_light_logo_gets_dark_backdrop(tmp_path: Path):
    light_logo = tmp_path / "light.png"
    Image.new("RGBA", (120, 40), (255, 255, 255, 255)).save(light_logo)

    bright = Image.new("RGB", (400, 300), (250, 250, 250))
    picked, backdrop = _pick_logo_path(bright, logo_on_dark_path=str(light_logo), logo_on_light_path=None)
    assert picked == Path(light_logo)
    assert backdrop == "dark"


def test_dark_background_picks_light_logo(tmp_path: Path):
    light_logo = tmp_path / "light.png"
    dark_logo = tmp_path / "dark.png"
    Image.new("RGBA", (120, 40), (255, 255, 255, 255)).save(light_logo)
    Image.new("RGBA", (120, 40), (0, 0, 0, 255)).save(dark_logo)

    dark = Image.new("RGB", (400, 300), (25, 30, 35))
    picked, backdrop = _pick_logo_path(
        dark, logo_on_dark_path=str(light_logo), logo_on_light_path=str(dark_logo)
    )
    assert picked == Path(light_logo)
    assert backdrop is None


def test_preferred_light_background_forces_dark_logo(tmp_path: Path):
    light_logo = tmp_path / "light.png"
    dark_logo = tmp_path / "dark.png"
    Image.new("RGBA", (120, 40), (255, 255, 255, 255)).save(light_logo)
    Image.new("RGBA", (120, 40), (20, 20, 20, 255)).save(dark_logo)

    # Image is dark overall but we force light-bg treatment for logo
    dark = Image.new("RGB", (400, 300), (25, 30, 35))
    picked, backdrop = _pick_logo_path(
        dark,
        logo_on_dark_path=str(light_logo),
        logo_on_light_path=str(dark_logo),
        preferred_background="light",
    )
    assert picked == Path(dark_logo)
    assert backdrop is None


def test_preferred_dark_background_forces_white_logo(tmp_path: Path):
    light_logo = tmp_path / "light.png"
    dark_logo = tmp_path / "dark.png"
    Image.new("RGBA", (120, 40), (255, 255, 255, 255)).save(light_logo)
    Image.new("RGBA", (120, 40), (20, 20, 20, 255)).save(dark_logo)

    bright = Image.new("RGB", (400, 300), (250, 250, 250))
    picked, backdrop = _pick_logo_path(
        bright,
        logo_on_dark_path=str(light_logo),
        logo_on_light_path=str(dark_logo),
        preferred_background="dark",
    )
    assert picked == Path(light_logo)
    assert backdrop is None
    base = tmp_path / "photo.png"
    light_logo = tmp_path / "light.png"
    dark_logo = tmp_path / "dark.png"

    img = Image.new("RGB", (800, 600), (200, 210, 220))
    for x in range(800):
        for y in range(120):
            img.putpixel((x, y), (248, 250, 252))
    img.save(base)
    Image.new("RGBA", (120, 40), (255, 255, 255, 255)).save(light_logo)
    Image.new("RGBA", (120, 40), (20, 20, 20, 255)).save(dark_logo)

    applied = apply_brand_to_image_path(
        base, logo_on_dark_path=str(light_logo), logo_on_light_path=str(dark_logo)
    )
    assert applied is True
