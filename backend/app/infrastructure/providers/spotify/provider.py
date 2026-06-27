"""Spotify provider scaffold – implement OAuth + Web API when credentials are configured."""

import structlog

from app.config import settings
from app.domain.entities import ProviderTrack
from app.domain.interfaces import MusicProvider

logger = structlog.get_logger()


class SpotifyProvider(MusicProvider):
    """
    Future: Spotify Web API integration.
    Requires SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET.
    """

    @property
    def name(self) -> str:
        return "spotify"

    def _configured(self) -> bool:
        return bool(settings.spotify_client_id and settings.spotify_client_secret)

    async def search(self, query: str, limit: int = 20) -> list[ProviderTrack]:
        if not self._configured():
            logger.warning("spotify_not_configured")
            return []
        # TODO: Implement Spotify search API
        raise NotImplementedError("Spotify integration pending – configure credentials")

    async def get_metadata(self, provider_track_id: str) -> ProviderTrack:
        if not self._configured():
            raise RuntimeError("Spotify not configured")
        raise NotImplementedError("Spotify integration pending")
