from types import SimpleNamespace
from uuid import uuid4

from app.application.services.memory_service import HeardSongSnapshot
from app.application.services.queue_service import QueueService
from app.infrastructure.database.models import QueueItemModel


def _candidate(provider_track_id: str, canonical_song_id=None):
    return SimpleNamespace(
        track=SimpleNamespace(
            provider_track_id=provider_track_id,
            canonical_song_id=canonical_song_id,
        )
    )


def _svc(**kwargs) -> QueueService:
    return QueueService(
        recommendation_engine=SimpleNamespace(),
        memory_service=SimpleNamespace(),
        normalizer=SimpleNamespace(),
        **kwargs,
    )


class TestSkipRecommendationCandidate:
    def setup_method(self):
        self.svc = _svc()

    def test_skips_track_already_in_queue(self):
        existing_tracks = {"vid-1"}
        assert self.svc._skip_recommendation_candidate(
            _candidate("vid-1", uuid4()), existing_tracks, set(), set()
        )

    def test_skips_song_already_in_queue(self):
        song_id = uuid4()
        assert self.svc._skip_recommendation_candidate(
            _candidate("vid-2", song_id), set(), {song_id}, set()
        )

    def test_skips_blocked_song(self):
        song_id = uuid4()
        assert self.svc._skip_recommendation_candidate(
            _candidate("vid-3", song_id), set(), set(), {song_id}
        )

    def test_allows_new_candidate(self):
        song_id = uuid4()
        assert not self.svc._skip_recommendation_candidate(
            _candidate("vid-4", song_id), set(), set(), set()
        )


class TestHeardQueueItem:
    def setup_method(self):
        self.svc = _svc()
        self.song_id = uuid4()
        self.item = QueueItemModel(
            user_id=uuid4(),
            song_id=self.song_id,
            provider="youtube",
            provider_track_id="vid-heard",
            title="Kalaimane",
            artist="Hariharan",
            position=1,
            is_current=False,
        )

    def test_matches_blocked_song_id(self):
        heard = [
            HeardSongSnapshot(
                song_id=self.song_id,
                title="Other Title",
                artist="Other Artist",
                duration_seconds=200,
            )
        ]
        assert self.svc._is_heard_queue_item(self.item, {self.song_id}, heard)

    def test_matches_semantic_history_entry(self):
        heard = [
            HeardSongSnapshot(
                song_id=uuid4(),
                title="Kalaimane",
                artist="Hariharan",
                duration_seconds=200,
            )
        ]
        assert self.svc._is_heard_queue_item(self.item, set(), heard)

    def test_allows_unheard_song(self):
        heard = [
            HeardSongSnapshot(
                song_id=uuid4(),
                title="Different Song",
                artist="Different Artist",
                duration_seconds=200,
            )
        ]
        assert not self.svc._is_heard_queue_item(self.item, set(), heard)


class TestNormalizeSeeds:
    def setup_method(self):
        self.svc = _svc()

    def test_trims_dedupes_and_caps(self):
        seeds = self.svc._normalize_seeds(
            ["  Coldplay ", "coldplay", "Ilaiyaraaja", "", "A", "B", "C", "D"]
        )
        assert seeds == ["Coldplay", "Ilaiyaraaja", "A", "B", "C"]

    def test_empty(self):
        assert self.svc._normalize_seeds(None) == []
        assert self.svc._normalize_seeds([]) == []


class TestInterleaveSeedQueries:
    def setup_method(self):
        self.svc = _svc()

    def test_round_robins_across_seeds(self):
        queries = self.svc._interleave_seed_queries(
            ["Alpha", "Beta"],
            ["english"],
        )
        # First variant of each seed before second variants (round-robin).
        assert any("Alpha" in q for q in queries[:2])
        assert any("Beta" in q for q in queries[:2])
        # Escape-hatch random discovery is always appended.
        assert len(queries) >= 7

    def test_build_uses_multiple_active_seeds(self):
        pref = SimpleNamespace(
            active_search_query="legacy",
            active_search_queries=["Rahman", "Coldplay"],
            preferred_languages=["english"],
            language_preference=None,
            discovery_year_from=None,
            discovery_year_to=None,
        )
        queries = self.svc._build_discovery_queries(pref)
        joined = " ".join(queries).lower()
        assert "rahman" in joined
        assert "coldplay" in joined
