from types import SimpleNamespace
from uuid import uuid4

from app.application.services.queue_service import QueueService


def _candidate(provider_track_id: str, canonical_song_id=None):
    return SimpleNamespace(
        track=SimpleNamespace(
            provider_track_id=provider_track_id,
            canonical_song_id=canonical_song_id,
        )
    )


class TestSkipRecommendationCandidate:
    def setup_method(self):
        self.svc = QueueService(
            recommendation_engine=SimpleNamespace(),
            memory_service=SimpleNamespace(),
            normalizer=SimpleNamespace(),
        )

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
