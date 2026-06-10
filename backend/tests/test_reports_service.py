from app.services.reports_service import _build_narrative


def test_narrative_includes_visibility_delta():
    text = _build_narrative(
        month_label="April 2026",
        keyword="digital marketing",
        vis_start=42.0,
        vis_end=51.5,
        top3_start=3,
        top3_end=5,
        pages_published=2,
        citations_ok=1,
        gbp_posts=1,
        in_progress=False,
    )
    assert "42" in text
    assert "51.5" in text
    assert "Top-3" in text
