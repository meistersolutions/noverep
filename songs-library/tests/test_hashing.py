from app.services.hashing import content_hash


def test_content_hash_stable():
    a = content_hash("Raja Raja Chozhan", "Rettai Vaal Kuruvi")
    b = content_hash("raja raja chozhan", "Rettai Vaal Kuruvi!")
    assert a == b


def test_content_hash_differs_by_movie():
    a = content_hash("Song", "Movie A")
    b = content_hash("Song", "Movie B")
    assert a != b


def test_content_hash_ignores_composer_and_year():
    a = content_hash("Song", "Movie", "Composer A", 1990)
    b = content_hash("Song", "Movie", "Composer B", 2000)
    assert a == b
