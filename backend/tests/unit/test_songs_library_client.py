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


async def test_resolve_youtube_many_parallel_and_skips_failures(monkeypatch):
    monkeypatch.setattr(
        "app.infrastructure.external.songs_library_client.settings.songs_library_enabled",
        True,
    )
    client = SongsLibraryClient(base_url="http://library.test")

    async def fake_one(song_id: str):
        if song_id == "fail":
            return None
        return LibrarySong(
            id=song_id,
            song_name=song_id,
            youtube_video_id=f"vid_{song_id}"[:11].ljust(11, "x"),
            playability="mapped",
        )

    monkeypatch.setattr(client, "resolve_youtube_for_song", fake_one)
    out = await client.resolve_youtube_many(["a", "fail", "b", "a"], concurrency=2)
    assert set(out) == {"a", "b"}
    assert out["a"].youtube_video_id
    assert "fail" not in out
