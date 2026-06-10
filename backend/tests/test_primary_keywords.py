from app.lib.primary_keywords import (
    normalize_primary_keywords,
    parse_primary_keywords,
    scan_keyword_from_primary,
)


def test_parse_primary_keywords():
    assert parse_primary_keywords("digital marketing, seo services") == [
        "digital marketing",
        "seo services",
    ]
    assert parse_primary_keywords("plumber; electrician\nfinance broker") == [
        "plumber",
        "electrician",
        "finance broker",
    ]
    assert parse_primary_keywords("seo, SEO,  ppc ") == ["seo", "ppc"]


def test_normalize_primary_keywords():
    assert normalize_primary_keywords("  seo ,  ppc  ") == "seo, ppc"


def test_scan_keyword_from_primary():
    assert scan_keyword_from_primary("digital marketing, seo services") == "digital marketing"
    assert scan_keyword_from_primary("  ") == ""
