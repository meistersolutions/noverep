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

    def test_rejects_concert(self):
        assert not is_single_song_track("Artist - Live at Wembley Stadium 2019", 300)

    def test_rejects_instrumental(self):
        assert not is_single_song_track("Song Name - Piano Cover", 240)


class TestAnyVideoFilter:
    def test_accepts_long_non_song_title(self):
        from app.domain.entities import ProviderTrack
        from app.infrastructure.providers.youtube.song_filter import filter_any_video_tracks

        tracks = [
            ProviderTrack(
                provider="youtube",
                provider_track_id="1",
                title="3 Hour Study With Me",
                artist="Channel",
                album=None,
                duration_seconds=10800,
                thumbnail_url=None,
                content_kind="video",
            )
        ]
        assert len(filter_any_video_tracks(tracks, 5)) == 1
