from app.lib.report_pdf import render_monthly_report_pdf


def test_render_monthly_report_pdf_bytes():
    pdf = render_monthly_report_pdf(
        business_name="ClickTrends",
        month_label="April 2026",
        keyword="digital marketing",
        report={
            "visibility_score_start": 40.0,
            "visibility_score_end": 52.5,
            "top3_start": 2,
            "top3_end": 5,
            "pages_published": 1,
            "gbp_posts": 2,
            "citations_fixed": 3,
            "reviews_new": None,
            "narrative_text": "Monthly SEO summary for April 2026.",
        },
    )
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 500
