from app.services.hashing import content_hash


def test_content_hash_stable():
    a = content_hash("Raja Raja Chozhan", "Rettai Vaal Kuruvi", "Ilaiyaraaja", 1987)
    b = content_hash("raja raja chozhan", "Rettai Vaal Kuruvi!", "Ilaiyaraaja", 1987)
    assert a == b


def test_content_hash_differs_by_movie():
    a = content_hash("Song", "Movie A", "Composer", 1990)
    b = content_hash("Song", "Movie B", "Composer", 1990)
    assert a != b
