from app.services.hashing import content_hash


def test_content_hash_stable():
    a = content_hash("Raja Raja Chozhan", "Rettai Vaal Kuruvi", release_year=1987, language="Tamil")
    b = content_hash("raja raja chozhan", "Rettai Vaal Kuruvi!", release_year=1987, language="tamil")
    assert a == b


def test_content_hash_differs_by_movie():
    a = content_hash("Song", "Movie A")
    b = content_hash("Song", "Movie B")
    assert a != b


def test_content_hash_differs_by_year_and_language():
    base = content_hash("Song", "Movie", release_year=1989, language="Tamil")
    other_year = content_hash("Song", "Movie", release_year=1990, language="Tamil")
    other_lang = content_hash("Song", "Movie", release_year=1989, language="Telugu")
    assert base != other_year
    assert base != other_lang


def test_content_hash_ignores_composer():
    a = content_hash("Song", "Movie", "Composer A", 1990, "Tamil")
    b = content_hash("Song", "Movie", "Composer B", 1990, "Tamil")
    assert a == b
