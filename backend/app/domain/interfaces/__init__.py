from abc import ABC, abstractmethod

from app.domain.entities import ProviderTrack, ScoredCandidate


class MusicProvider(ABC):
    """Abstract music provider – business logic depends on this interface only."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def search(
        self,
        query: str,
        limit: int = 20,
        *,
        raw: bool = False,
        songs_only: bool = True,
    ) -> list[ProviderTrack]:
        ...

    @abstractmethod
    async def get_metadata(
        self, provider_track_id: str, *, songs_only: bool = True
    ) -> ProviderTrack:
        ...

    async def get_stream_url(self, provider_track_id: str) -> str | None:
        """Optional direct stream URL; YouTube uses iframe on client."""
        return None


class RecommendationEnginePort(ABC):
    @abstractmethod
    async def recommend_next(
        self,
        user_id: str,
        seed_query: str | None,
        exclude_canonical_ids: set[str],
        recent_artists: list[str],
        recent_genres: list[str],
        limit: int = 10,
    ) -> list[ScoredCandidate]:
        ...


class SongNormalizerPort(ABC):
    @abstractmethod
    def normalize_key(self, title: str, artist: str, duration_seconds: int | None) -> str:
        ...

    @abstractmethod
    async def resolve_canonical(self, track: ProviderTrack) -> str:
        ...
