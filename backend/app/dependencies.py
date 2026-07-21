from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.home_recommendations import HomeRecommendationService
from app.application.services.lyrics_service import LyricsService
from app.application.services.memory_service import MemoryService
from app.application.services.playlist_service import PlaylistService
from app.application.services.queue_service import QueueService
from app.application.services.recommendation_engine import RecommendationEngine
from app.application.services.song_enrichment_service import SongEnrichmentService
from app.application.services.song_normalizer import SongNormalizer
from app.application.services.statistics_service import StatisticsService
from app.config import settings
from app.infrastructure.auth.auth_service import AuthService, decode_token
from app.infrastructure.database.models import UserModel
from app.infrastructure.database.session import get_db_session
from app.infrastructure.providers.spotify.provider import SpotifyProvider
from app.infrastructure.providers.youtube.provider import YouTubeProvider
from app.infrastructure.external.musicbrainz_client import MusicBrainzClient

security = HTTPBearer(auto_error=False)

# Singleton service instances
_youtube = YouTubeProvider()
_spotify = SpotifyProvider()
_providers = {"youtube": _youtube, "spotify": _spotify}
_normalizer = SongNormalizer()
_memory = MemoryService()
_recommendation = RecommendationEngine(_providers, _memory, _normalizer)
_home = HomeRecommendationService(_recommendation)
_queue = QueueService(_recommendation, _memory, _normalizer, home_recommendations=_home)
_playlist = PlaylistService(_normalizer)
_auth = AuthService()
_stats = StatisticsService()
_musicbrainz = MusicBrainzClient(settings.musicbrainz_user_agent)
_enrichment = SongEnrichmentService(_musicbrainz)
_lyrics = LyricsService()


def get_providers() -> dict:
    return _providers


def get_memory_service() -> MemoryService:
    return _memory


def get_recommendation_engine() -> RecommendationEngine:
    return _recommendation


def get_queue_service() -> QueueService:
    return _queue


def get_playlist_service() -> PlaylistService:
    return _playlist


def get_auth_service() -> AuthService:
    return _auth


def get_statistics_service() -> StatisticsService:
    return _stats


def get_home_recommendations_service() -> HomeRecommendationService:
    return _home


def get_normalizer() -> SongNormalizer:
    return _normalizer


def get_enrichment_service() -> SongEnrichmentService:
    return _enrichment


def get_lyrics_service() -> LyricsService:
    return _lyrics


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_db_session),
) -> UserModel:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = UUID(payload["sub"])
    result = await session.execute(select(UserModel).where(UserModel.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def get_admin_user(user: UserModel = Depends(get_current_user)) -> UserModel:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
