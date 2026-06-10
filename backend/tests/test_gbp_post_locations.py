from app.services.gbp_service import _sanitize_post_locations


def test_city_mode_strips_suburb_and_dedupes_city():
    body = (
        "For businesses in Essendon, VIC, social media matters. "
        "Melbourne businesses need Melbourne content that feels local."
    )
    out = _sanitize_post_locations(
        body,
        location_scope="city",
        location_label="Melbourne",
        location_full="Melbourne, VIC",
        city_name="Melbourne",
        target_keyword="digital marketing melbourne",
        forbidden_names=["Essendon"],
    )
    assert "essendon" not in out.lower(), f"Essendon should be removed: {out}"
    # Only one Melbourne reference should remain
    assert out.lower().count("melbourne") <= 1, f"Melbourne repeated: {out}"


def test_suburb_mode_removes_city_and_dedupes_suburb():
    body = (
        "For businesses in Essendon, VIC, organic social content is underused. "
        "With Essendon's tight-knit community and foot traffic around Essendon's main strips, "
        "consistent content from our Digital Marketing services Melbourne team helps every day."
    )
    out = _sanitize_post_locations(
        body,
        location_scope="suburb",
        location_label="Essendon",
        location_full="Essendon, VIC",
        city_name="Melbourne",
        target_keyword="digital marketing essendon",
        forbidden_names=[],
    )
    assert "melbourne" not in out.lower(), f"Melbourne should be removed: {out}"
    # Essendon should appear only once (the first mention), rest replaced with "the suburb"
    assert out.lower().count("essendon") == 1, f"Essendon repeated: {out}"
    assert "the suburb" in out.lower(), f"Should have replacement: {out}"


def test_suburb_mode_possessive_replaced_gracefully():
    body = "Around Essendon's main strips, businesses thrive. Essendon is a great suburb."
    out = _sanitize_post_locations(
        body,
        location_scope="suburb",
        location_label="Essendon",
        location_full="Essendon, VIC",
        city_name="Melbourne",
        target_keyword="local seo essendon",
        forbidden_names=[],
    )
    assert out.lower().count("essendon") == 1
    assert "the suburb's" in out.lower() or "the suburb" in out.lower()
