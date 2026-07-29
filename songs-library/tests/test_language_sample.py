from app.routers.api import _language_match_terms


def test_language_match_terms_expands_aliases():
    terms = _language_match_terms(["tamil"])
    lowered = {t.casefold() for t in terms}
    assert "tamil" in lowered
    assert "ta" in lowered


def test_language_match_terms_dedupes_and_ignores_blank():
    terms = _language_match_terms(["Tamil", "tamil", "", "  "])
    assert len([t for t in terms if t.casefold() == "tamil"]) == 1
