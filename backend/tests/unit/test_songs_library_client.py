from app.infrastructure.external.songs_library_client import LibrarySong, SongsLibraryClient


def test_library_song_from_dict_and_search_query():
    song = LibrarySong.from_dict(
        {
            "id": "abc",
            "song_name": "Thenpandi Cheemayile",
            "movie_name": "Nayakan",
            "composer_name": "Ilaiyaraaja",
            "singers": ["Kamal Haasan"],
            "content_hash": "hash1",
            "popularity": 90,
        }
    )
    assert song.song_name == "Thenpandi Cheemayile"
    assert "Nayakan" in song.search_query()
    assert "official audio" in song.search_query()


def test_client_disabled_without_url(monkeypatch):
    monkeypatch.setattr(
        "app.infrastructure.external.songs_library_client.settings.songs_library_url",
        "",
    )
    monkeypatch.setattr(
        "app.infrastructure.external.songs_library_client.settings.songs_library_enabled",
        True,
    )
    client = SongsLibraryClient(base_url="")
    assert client.enabled is False
