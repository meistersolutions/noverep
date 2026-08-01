from app.services.seed_match import seed_match_filters


def test_seed_match_filters_cover_credit_fields():
    clauses = seed_match_filters("Yesudas")
    assert len(clauses) >= 8


def test_seed_match_filters_empty_seed():
    assert seed_match_filters("") == []
    assert seed_match_filters("   ") == []
