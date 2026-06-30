import pytest
from unittest.mock import AsyncMock, MagicMock

from app.application.services.recommendation_engine import RecommendationEngine, _safe_lower
from app.domain.entities import ProviderTrack


class TestSafeLower:
    def test_none_returns_empty(self):
        assert _safe_lower(None) == ""

    def test_strips_and_lowercases(self):
        assert _safe_lower("  Foo  ") == "foo"


class TestApplyUserBlocks:
    @pytest.mark.asyncio
    async def test_handles_missing_artist_and_title(self):
        engine = RecommendationEngine({}, None, None)
        session = AsyncMock()
        prefs = MagicMock()
        prefs.blocked_artists = ["blocked artist"]
        prefs.blocked_albums = []
        prefs.blocked_songs = []
        result = MagicMock()
        result.scalar_one_or_none.return_value = prefs
        session.execute.return_value = result

        tracks = [
            ProviderTrack(
                provider="youtube",
                provider_track_id="1",
                title="Song",
                artist="",
                album=None,
                duration_seconds=200,
                thumbnail_url=None,
            ),
            ProviderTrack(
                provider="youtube",
                provider_track_id="2",
                title="Other",
                artist="Blocked Artist",
                album=None,
                duration_seconds=200,
                thumbnail_url=None,
            ),
        ]

        filtered = await engine._apply_user_blocks(session, "user-id", tracks)
        assert len(filtered) == 1
        assert filtered[0].provider_track_id == "1"


class TestRawSearch:
    @pytest.mark.asyncio
    async def test_raw_search_uses_literal_query(self):
        from app.domain.entities import ProviderTrack

        track = ProviderTrack(
            provider="youtube",
            provider_track_id="abc",
            title="Song",
            artist="Artist",
            album=None,
            duration_seconds=200,
            thumbnail_url=None,
        )

        class FakeProvider:
            name = "youtube"

            async def search(self, query: str, limit: int = 20, *, raw: bool = False):
                assert raw is True
                assert query == "exact query"
                return [track]

        engine = RecommendationEngine({"youtube": FakeProvider()}, None, None)
        results = await engine.raw_search("exact query", limit=5)
        assert len(results) == 1
        assert results[0].track.provider_track_id == "abc"
