from app.services.gbp_service import build_gbp_call_to_action, google_gbp_call_to_action


def test_call_cta_never_includes_phone_number():
    cta = build_gbp_call_to_action("CALL", phone="+61370209120")
    assert cta == {"actionType": "CALL"}
    assert "phoneNumber" not in cta

    google_cta = google_gbp_call_to_action({"actionType": "CALL", "phoneNumber": "+61370209120"})
    assert google_cta == {"actionType": "CALL"}
    assert "phoneNumber" not in google_cta


def test_learn_more_cta_includes_url():
    cta = build_gbp_call_to_action(
        "LEARN_MORE",
        url="clicktrends.com.au/contact-us/",
    )
    assert cta == {
        "actionType": "LEARN_MORE",
        "url": "https://clicktrends.com.au/contact-us/",
    }
    assert google_gbp_call_to_action(cta) == cta


def test_none_cta_returns_none():
    assert build_gbp_call_to_action("NONE") is None
    assert build_gbp_call_to_action(None) is None
