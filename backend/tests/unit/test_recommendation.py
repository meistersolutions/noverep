import pytest
from app.application.services.song_normalizer import SongNormalizer, _normalize_text


class TestSongNormalizer:
    def test_normalize_key_consistent(self):
        n = SongNormalizer()
        k1 = n.normalize_key("Bohemian Rhapsody", "Queen", 354)
        k2 = n.normalize_key("Bohemian Rhapsody", "Queen", 354)
        assert k1 == k2

    def test_normalize_key_different_artists(self):
        n = SongNormalizer()
        k1 = n.normalize_key("Song", "Artist A", 200)
        k2 = n.normalize_key("Song", "Artist B", 200)
        assert k1 != k2

    def test_normalize_text(self):
        assert _normalize_text("Hello, World!") == "hello world"


class TestMemoryWindow:
    def test_memory_window_days(self):
        from app.domain.enums import MEMORY_WINDOW_DAYS, MemoryWindow

        assert MEMORY_WINDOW_DAYS[MemoryWindow.ONE_DAY] == 1
        assert MEMORY_WINDOW_DAYS[MemoryWindow.FOREVER] is None


class TestRecommendationScoring:
    def test_score_penalizes_recent_artist(self):
        from app.application.services.recommendation_engine import RecommendationEngine
        from app.domain.entities import ProviderTrack, RecommendationWeights

        engine = RecommendationEngine({}, None, None)
        track = ProviderTrack(
            provider="youtube",
            provider_track_id="1",
            title="Test",
            artist="Same Artist",
            album="Album",
            duration_seconds=200,
            thumbnail_url=None,
            genre="pop",
        )
        weights = RecommendationWeights()
        scored_with = engine._score_track(track, weights, ["Same Artist"], [], [], [], [])
        scored_without = engine._score_track(track, weights, [], [], [], [], [])
        assert scored_with.score < scored_without.score
