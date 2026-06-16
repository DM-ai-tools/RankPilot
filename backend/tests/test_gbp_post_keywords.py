from app.services.gbp_service import (
    _parse_post_prompt_slots,
    _parse_structured_prompt_slot,
    _resolve_target_keyword_from_prompt,
    _strip_design_artifacts_from_post,
)


AHREFS = [
    "digital marketing service australia by twastia.com",
    "Digital Marketing services Melbourne",
    "seo melbourne",
]


def test_prompt_slot_preserves_empty_lines():
    slots = _parse_post_prompt_slots("Digital Marketing services Melbourne\n\nseo tips", 3)
    assert slots == ["Digital Marketing services Melbourne", None, "seo tips"]


def test_prompt_slot_comma_phrase_goes_to_slot_0_not_split():
    # Commas inside a keyword phrase must NOT split into multiple slots.
    slots = _parse_post_prompt_slots("digital marketing, seo agency, seo agency in melbourne Essendon", 3)
    assert slots[0] == "digital marketing, seo agency, seo agency in melbourne Essendon"
    assert slots[1] is None
    assert slots[2] is None


def test_clicked_keyword_becomes_target_not_first_ahrefs():
    kw, direction, image_theme = _resolve_target_keyword_from_prompt(
        "Digital Marketing services Melbourne",
        AHREFS,
        AHREFS[0],
    )
    assert kw == "Digital Marketing services Melbourne"
    assert direction is None
    assert image_theme is None


def test_comma_prompt_splits_direction_and_keyword():
    kw, direction, image_theme = _resolve_target_keyword_from_prompt(
        "focus on reviews, Digital Marketing services Melbourne",
        AHREFS,
        AHREFS[0],
    )
    assert kw == "Digital Marketing services Melbourne"
    assert direction == "focus on reviews"
    assert image_theme is None


def test_empty_prompt_uses_ahrefs_fallback():
    kw, direction, image_theme = _resolve_target_keyword_from_prompt(None, AHREFS, AHREFS[0])
    assert kw == AHREFS[0]
    assert direction is None
    assert image_theme is None


def test_researched_keyword_not_in_ahrefs_list():
    kw, direction, image_theme = _resolve_target_keyword_from_prompt(
        "seo specialist melbourne",
        AHREFS,
        AHREFS[0],
    )
    assert kw == "seo specialist melbourne"
    assert direction is None
    assert image_theme is None
    kw, direction, image_theme = _resolve_target_keyword_from_prompt(
        "custom local seo phrase",
        AHREFS,
        AHREFS[0],
    )
    assert kw == "custom local seo phrase"
    assert direction is None
    assert image_theme is None


def test_structured_slot_uses_post_angle_not_image_prompt_for_copy():
    slot = (
        "Create a unique, professional Google Business Profile post photo.\n\n"
        "CORE KEYWORD: Digital Marketing services Melbourne\n"
        "VISUAL HOOK: Team reviewing SEO analytics.\n"
        "Brand colours: primary #FF5F32, secondary #000000\n\n"
        "STRICT RULES: NO text in image.\n\n"
        "---\nPost angle (for copy): Boost organic reach with tailored SEO.\n"
        "KEYWORD: Digital Marketing services Melbourne"
    )
    kw, direction, image_theme = _resolve_target_keyword_from_prompt(slot, AHREFS, AHREFS[0])
    assert kw == "Digital Marketing services Melbourne"
    assert direction == "Boost organic reach with tailored SEO."
    assert "VISUAL HOOK" in (image_theme or "")
    assert "#FF5F32" not in (direction or "")

    parsed_kw, image_prompt, post_angle = _parse_structured_prompt_slot(slot)
    assert parsed_kw == "Digital Marketing services Melbourne"
    assert "VISUAL HOOK" in (image_prompt or "")
    assert "organic reach" in (post_angle or "")


def test_image_brief_without_post_angle_does_not_become_copy_direction():
    brief = (
        "Create a unique, professional Google Business Profile post photo for ClickTrends. "
        "VISUAL HOOK: analytics dashboard. Brand colours #FF5F32 and #000000."
    )
    kw, direction, image_theme = _resolve_target_keyword_from_prompt(brief, AHREFS, AHREFS[0])
    assert kw == AHREFS[0]
    assert direction is None
    assert image_theme == brief


def test_strip_design_artifacts_removes_hex_codes():
    raw = (
        "Our brand colours (#FF5F32 and #000000) run through the composition "
        "like a thread, tying energy to precision."
    )
    cleaned = _strip_design_artifacts_from_post(raw)
    assert "#FF5F32" not in cleaned
    assert "#000000" not in cleaned
    assert "run through the composition" in cleaned
