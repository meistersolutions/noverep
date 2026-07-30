from types import SimpleNamespace
from unittest.mock import patch

from app.services.youtube_resolve import (
    _data_api_configured,
    _search_youtube_sync,
    build_search_queries,
    search_youtube_for_song,
)


def test_build_search_queries_dedupes_and_broadens():
    song = SimpleNamespace(
        song_name="Iraikka Iraikka",
        movie_name="Karuppu Panam",
        composer_name="M. S. Viswanathan",
    )
    queries = build_search_queries(song)
    assert queries[0].endswith("official audio")
    assert "Karuppu Panam" in queries[1]
    assert "M. S. Viswanathan" in queries[2]
    assert queries[-1] == "Iraikka Iraikka"
    assert len(queries) == len(set(q.casefold() for q in queries))


def test_search_youtube_sync_skips_ytdlp_when_api_key_set(monkeypatch):
    monkeypatch.setattr(
        "app.services.youtube_resolve.settings.youtube_api_key",
        "test-key",
    )
    monkeypatch.setattr(
        "app.services.youtube_resolve._search_via_data_api",
        lambda *_a, **_k: (None, None),
    )
    with patch("yt_dlp.YoutubeDL") as ydl:
        assert _search_youtube_sync("query", language="Tamil") == (None, None)
        ydl.assert_not_called()


def test_search_youtube_for_song_tries_multiple_queries(monkeypatch):
    song = SimpleNamespace(
        song_name="Song",
        movie_name="Movie",
        composer_name="Composer",
        language="Tamil",
    )
    monkeypatch.setattr(
        "app.services.youtube_resolve.settings.youtube_api_key",
        "test-key",
    )
    seen: list[str] = []

    def fake_search(query, *, language=None):
        seen.append(query)
        if query == "Song Movie":
            return "abcdefghijk", 1000
        return None, None

    monkeypatch.setattr(
        "app.services.youtube_resolve._search_youtube_sync",
        fake_search,
    )
    vid, views = search_youtube_for_song(song)
    assert vid == "abcdefghijk"
    assert views == 1000
    assert len(seen) >= 2
    assert _data_api_configured()
