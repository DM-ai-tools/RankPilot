from app.schemas.keywords import RelatedKeywordIdea, SuburbKeywordPhrase
from app.services.keyword_research_service import (
    _build_top_keywords,
    _is_junk_keyword,
    _is_relevant_local_keyword,
)


def test_junk_keyword_filters_urls():
    assert _is_junk_keyword("digital marketing service australia by twastia.com") is True
    assert _is_junk_keyword("Digital Marketing services Melbourne") is False


def test_relevant_local_requires_location_and_service():
    assert _is_relevant_local_keyword(
        "Digital Marketing services Melbourne",
        "digital marketing",
        ["Melbourne"],
    )
    assert not _is_relevant_local_keyword(
        "random seo tips",
        "digital marketing",
        ["Melbourne"],
    )


def test_build_top_keywords_ranks_phrases_first():
    phrases = [
        SuburbKeywordPhrase(
            keyword="digital marketing Melbourne",
            suburb="Melbourne",
            avg_monthly_searches=500,
            opportunity_score=400,
        ),
    ]
    related = [
        RelatedKeywordIdea(
            keyword="digital marketing service australia by twastia.com",
            avg_monthly_searches=100,
            opportunity_score=90,
        ),
        RelatedKeywordIdea(
            keyword="Melbourne digital marketing agency",
            suburb="Melbourne",
            avg_monthly_searches=300,
            opportunity_score=250,
        ),
    ]
    top = _build_top_keywords(
        phrases,
        related,
        primary="digital marketing",
        location_names=["Melbourne"],
        limit=10,
    )
    kws = [t.keyword for t in top]
    assert "digital marketing Melbourne" in kws
    assert "Melbourne digital marketing agency" in kws
    assert "digital marketing service australia by twastia.com" not in kws
    assert kws[0] == "digital marketing Melbourne"
