from app.services.gbp_image_prompt_service import looks_like_full_runway_prompt


def test_detects_full_runway_prompt():
    text = (
        "Create a unique, professional Google Business Profile post photo for Acme.\n\n"
        "CORE KEYWORD: digital marketing melbourne\n\n"
        "VISUAL HOOK: A strategist reviews campaign dashboards with warm light.\n\n"
        "CREATIVE ARCHETYPE: DATA_DRIVEN\n\n"
        "STRICT RULES: NO text, words, logos, or watermarks anywhere in the image."
    )
    assert looks_like_full_runway_prompt(text) is True


def test_rejects_short_theme():
    assert looks_like_full_runway_prompt("SEO tips for local business") is False
