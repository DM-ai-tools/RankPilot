"""FAQ accordion conversion for local SEO module M."""

from app.services.local_seo_page_service import (
    modules_to_markdown,
    normalize_modules,
    parse_faq_pairs,
    sanitize_module_body,
)
from app.services.wordpress_publish_service import _markdown_to_html


def test_parse_faq_pairs():
    body = (
        "**How is SEO in Malvern different?**\n"
        "Professional buyers research more before contacting you.\n\n"
        "**How long until results?**\n"
        "Most firms see movement in a few months."
    )
    pairs = parse_faq_pairs(body)
    assert len(pairs) == 2
    assert pairs[0][0] == "How is SEO in Malvern different?"
    assert "Professional buyers" in pairs[0][1]
    assert pairs[1][0] == "How long until results?"


def test_modules_to_markdown_tags_module_m_faq():
    modules = [
        {"type": "A", "heading": "Hero", "body": "Intro paragraph."},
        {
            "type": "M",
            "heading": "SEO questions from Malvern firms",
            "body": "**What is local SEO?**\nAnswer one.\n\n**Do you serve Malvern East?**\nAnswer two.",
        },
    ]
    md = modules_to_markdown(modules, h1="AI SEO Company Malvern")
    assert "<!--RANKPILOT_FAQ_MD-->" in md
    assert "**What is local SEO?**" in md
    assert "rankpilot-faq-accordion" not in md


def test_markdown_to_html_preserves_faq_accordion():
    md = (
        "# Title\n\nSome intro.\n\n"
        "## FAQ for Malvern\n\n<!--RANKPILOT_FAQ_MD-->\n"
        "**Question one?**\nAnswer one.\n\n**Question two?**\nAnswer two.\n\n"
        "## Final CTA\n\nCall us."
    )
    html = _markdown_to_html(md)
    assert "rankpilot-faq-accordion" in html
    assert "<details" in html
    assert "Question one?" in html
    assert 'text-align:left' in html
    assert "Question one?" in html
    assert "**Question" not in html
    assert "rankpilot-faq-accordion" in html


def test_sanitize_module_body_unwraps_shouty_bold():
    raw = (
        "**HOW SEO REALLY WORKS - EXPLAINED FOR ADELAIDE PROFESSIONALS**\n\n"
        "**CLICKTRENDS HELPS PROFESSIONAL SERVICE FIRMS IN ADELAIDE TURN SEARCH TRAFFIC INTO QUALITY ENQUIRIES EVERY MONTH.**"
    )
    cleaned = sanitize_module_body(raw, module_type="B")
    assert "HOW SEO" not in cleaned
    assert "How SEO Really Works" in cleaned
    assert "Clicktrends Helps" in cleaned or "Clicktrends helps" in cleaned


def test_normalize_modules_fixes_shouty_headings():
    modules = normalize_modules(
        [
            {
                "type": "H",
                "heading": "WHY ADELAIDE PROFESSIONAL SERVICES CHOOSE CLICKTRENDS",
                "body": "**LOCAL MARKET UNDERSTANDING**\nWe understand Adelaide search behaviour.",
            }
        ]
    )
    assert "Why Adelaide" in modules[0]["heading"]
    assert "**Local market understanding**" in modules[0]["body"].lower() or "**Local Market Understanding**" in modules[0]["body"]
    assert "### Local Market" not in modules[0]["body"]
