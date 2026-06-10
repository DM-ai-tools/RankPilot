from app.services.gbp_service import _fallback_gbp_direction, _pick_diverse_keywords


def test_pick_diverse_keywords_cycles():
    kws = ["a", "b"]
    assert _pick_diverse_keywords(kws, 4) == ["a", "b", "a", "b"]


def test_fallback_direction_includes_keyword():
    slot = _fallback_gbp_direction("Digital Marketing Melbourne", 0)
    assert "Digital Marketing Melbourne" in slot
    assert "SEO" in slot or "organic" in slot.lower()
