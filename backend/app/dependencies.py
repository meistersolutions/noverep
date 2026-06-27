from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.home_recommendations import HomeRecommendationService
from app.application.services.memory_service import MemoryService
from app.application.services.playlist_service import PlaylistService
from app.application.services.queue_service import QueueService
from app.application.services.recommendation_engine import RecommendationEngine
from app.application.services.song_normalizer import SongNormalizer
from app.application.services.statistics_service import StatisticsService
from app.infrastructure.auth.auth_service import AuthService, decode_token
from app.infrastructure.database.models import UserModel
from app.infrastructure.database.session import get_db_session
from app.infrastructure.providers.spotify.provider import SpotifyProvider
from app.infrastructure.providers.youtube.provider import YouTubeProvider

security = HTTPBearer(auto_error=False)

# Singleton service instances
_youtube = YouTubeProvider()
_spotify = SpotifyProvider()
_providers = {"youtube": _youtube, "spotify": _spotify}
_normalizer = SongNormalizer()
_memory = MemoryService()
_recommendation = RecommendationEngine(_providers, _memory, _normalizer)
_queue = QueueService(_recommendation, _memory, _normalizer)
_playlist = PlaylistService(_normalizer)
_auth = AuthService()
_stats = StatisticsService()
_home = HomeRecommendationService(_recommendation)


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
