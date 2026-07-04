"""Background MusicBrainz enrichment for canonical songs."""

import structlog
from uuid import UUID

from app.application.services.song_enrichment_service import SongEnrichmentService
from app.dependencies import get_enrichment_service, get_providers
from app.domain.entities import ProviderTrack
from app.infrastructure.database.models import SongModel
from app.infrastructure.database.session import async_session_factory
from sqlalchemy import select

logger = structlog.get_logger()


async def run_song_enrichment_background(
    song_id: UUID,
    provider: str,
    provider_track_id: str,
    title: str,
    artist: str,
    album: str | None,
    duration_seconds: int | None,
) -> None:
    enrichment_svc: SongEnrichmentService = get_enrichment_service()
    providers = get_providers()
    async with async_session_factory() as session:
        try:
            result = await session.execute(select(SongModel).where(SongModel.id == song_id))
            song = result.scalar_one_or_none()
            if not song:
                return

            track: ProviderTrack | None = None
            provider_impl = providers.get(provider)
            if provider_impl and provider_track_id:
                try:
                    track = await provider_impl.get_metadata(provider_track_id)
                except Exception:
                    track = None

            if not track:
                track = ProviderTrack(
                    provider=provider,
                    provider_track_id=provider_track_id,
                    title=title,
                    artist=artist,
                    album=album,
                    duration_seconds=duration_seconds,
                    thumbnail_url=None,
                )

            await enrichment_svc.enrich_and_persist(session, song, track)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("background_song_enrichment_failed", song_id=str(song_id))
