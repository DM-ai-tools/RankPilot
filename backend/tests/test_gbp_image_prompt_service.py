"""Tests for GBP Runway image prompt builder."""

from app.services.gbp_image_prompt_service import (
    backdrop_for_archetype,
    build_gbp_post_image_prompt,
    infer_keyword_intent,
    pick_archetype,
)


def test_infer_keyword_intent_commercial():
    assert infer_keyword_intent("google ads agency melbourne") == "commercial"


def test_infer_keyword_intent_transactional():
    assert infer_keyword_intent("free seo audit quote") == "transactional"


def test_pick_archetype_avoids_back_to_back():
    first = pick_archetype(keyword="seo melbourne", intent="commercial", last_archetype=None)
    second = pick_archetype(
        keyword="ppc management",
        intent="commercial",
        last_archetype=first,
        used_in_batch=[first],
        post_index=2,
    )
    assert second != first


def test_backdrop_for_archetype():
    assert backdrop_for_archetype("SOCIAL_PROOF") == "light"
    assert backdrop_for_archetype("AUTHORITY") == "dark"


def test_build_prompt_logo_zone_light_archetype():
    prompt, meta = build_gbp_post_image_prompt(
        keyword="seo melbourne",
        business_name="Clicktrends",
        archetype="SOCIAL_PROOF",
        post_index=1,
    )
    assert "top-left corner clean, bright white" in prompt.lower()
    assert meta["logo_background"] == "light"


def test_build_prompt_logo_zone_dark_archetype():
    prompt, meta = build_gbp_post_image_prompt(
        keyword="seo melbourne",
        business_name="Clicktrends",
        archetype="DATA_DRIVEN",
        post_index=1,
    )
    assert "top-left corner clean, dark navy" in prompt.lower()
    assert meta["logo_background"] == "dark"

    prompt, meta = build_gbp_post_image_prompt(
        keyword="digital marketing essendon",
        business_name="Clicktrends",
        metro="Melbourne",
        theme="Local SEO tips for small business",
        post_body="Want more local leads? Here is how we help.",
        brand_config={"primary_color": "#FF5F32", "secondary_color": "#1A1A2E"},
        archetype="DATA_DRIVEN",
        layout="centred hero subject with soft depth-of-field background",
        texture="flat clean background, no texture",
        composition="extra-sharp focal point with cinematic depth of field",
        post_index=1,
    )
    assert "digital marketing essendon" in prompt.lower()
    assert "no text" in prompt.lower()
    assert meta["archetype"] == "DATA_DRIVEN"
    assert meta["keyword"] == "digital marketing essendon"
