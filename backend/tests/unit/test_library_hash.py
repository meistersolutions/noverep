from app.application.services.library_hash import library_content_hash


def test_library_hash_matches_songs_library_normalization():
    a = library_content_hash("Raja Raja Chozhan", "Rettai Vaal Kuruvi", "Ilaiyaraaja", 1987)
    b = library_content_hash("raja raja chozhan", "Rettai Vaal Kuruvi!", "Ilaiyaraaja", 1987)
    assert a == b
