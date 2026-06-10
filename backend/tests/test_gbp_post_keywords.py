from app.services.gbp_service import (
    _parse_post_prompt_slots,
    _parse_structured_prompt_slot,
    _resolve_target_keyword_from_prompt,
)


AHREFS = [
    "digital marketing service australia by twastia.com",
    "Digital Marketing services Melbourne",
    "seo melbourne",
]


def test_prompt_slot_preserves_empty_lines():
    slots = _parse_post_prompt_slots("Digital Marketing services Melbourne\n\nseo tips", 3)
    assert slots == ["Digital Marketing services Melbourne", None, "seo tips"]


def test_clicked_keyword_becomes_target_not_first_ahrefs():
    kw, direction = _resolve_target_keyword_from_prompt(
        "Digital Marketing services Melbourne",
        AHREFS,
        AHREFS[0],
    )
    assert kw == "Digital Marketing services Melbourne"
    assert direction is None


def test_comma_prompt_splits_direction_and_keyword():
    kw, direction = _resolve_target_keyword_from_prompt(
        "focus on reviews, Digital Marketing services Melbourne",
        AHREFS,
        AHREFS[0],
    )
    assert kw == "Digital Marketing services Melbourne"
    assert direction == "focus on reviews"


def test_empty_prompt_uses_ahrefs_fallback():
    kw, direction = _resolve_target_keyword_from_prompt(None, AHREFS, AHREFS[0])
    assert kw == AHREFS[0]
    assert direction is None


def test_unknown_short_phrase_treated_as_keyword():
    kw, direction = _resolve_target_keyword_from_prompt(
        "custom local seo phrase",
        AHREFS,
        AHREFS[0],
    )
    assert kw == "custom local seo phrase"
    assert direction is None


def test_structured_slot_parses_keyword_and_image_prompt():
    slot = (
        "Create a unique, professional Google Business Profile post photo.\n\n"
        "CORE KEYWORD: Digital Marketing services Melbourne\n"
        "VISUAL HOOK: Team reviewing SEO analytics.\n\n"
        "STRICT RULES: NO text in image.\n\n"
        "---\nPost angle (for copy): Boost organic reach with tailored SEO.\n"
        "KEYWORD: Digital Marketing services Melbourne"
    )
    kw, direction = _resolve_target_keyword_from_prompt(slot, AHREFS, AHREFS[0])
    assert kw == "Digital Marketing services Melbourne"
    assert direction is not None
    assert "SEO analytics" in direction or "organic reach" in direction

    parsed_kw, image_prompt, post_angle = _parse_structured_prompt_slot(slot)
    assert parsed_kw == "Digital Marketing services Melbourne"
    assert "VISUAL HOOK" in (image_prompt or "")
    assert "organic reach" in (post_angle or "")
