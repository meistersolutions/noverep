from app.application.services.library_hash import library_content_hash


def test_library_hash_matches_songs_library_normalization():
    a = library_content_hash("Raja Raja Chozhan", "Rettai Vaal Kuruvi")
    b = library_content_hash("raja raja chozhan", "Rettai Vaal Kuruvi!")
    assert a == b


def test_library_hash_ignores_year_and_language():
    a = library_content_hash("Song", "Movie", release_year=1989, language="Tamil")
    b = library_content_hash("Song", "Movie", release_year=1990, language="Telugu")
    assert a == b
