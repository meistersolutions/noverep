import pytest

from app.infrastructure.providers.youtube.song_filter import (
    is_single_song_track,
    normalize_search_query,
)


class TestSongFilter:
    def test_normalize_adds_audio_suffix(self):
        assert "official audio" in normalize_search_query("drake").lower()

    def test_rejects_compilation(self):
        assert not is_single_song_track("Best of 90s Non Stop Bollywood Mix", 3600)

    def test_rejects_too_short(self):
        assert not is_single_song_track("Song", 20)

    def test_accepts_normal_song(self):
        assert is_single_song_track("Artist - Song Name (Official Audio)", 240)
