from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.song_normalizer import SongNormalizer
from app.domain.entities import ProviderTrack
from app.infrastructure.database.models import (
    ArtistModel,
    PlaylistItemModel,
    PlaylistModel,
    ProviderMappingModel,
    ProviderModel,
    SongModel,
)

logger = structlog.get_logger()

LIKED_SYSTEM_KEY = "liked"
LIKED_PLAYLIST_NAME = "Liked"


class PlaylistService:
    def __init__(self, normalizer: SongNormalizer):
        self.normalizer = normalizer

    async def ensure_liked_playlist(
        self, session: AsyncSession, user_id: UUID
    ) -> PlaylistModel:
        result = await session.execute(
            select(PlaylistModel).where(
                PlaylistModel.user_id == user_id,
                PlaylistModel.system_key == LIKED_SYSTEM_KEY,
            )
        )
        playlist = result.scalar_one_or_none()
        if playlist:
            return playlist

        playlist = PlaylistModel(
            user_id=user_id,
            name=LIKED_PLAYLIST_NAME,
            description="Songs you liked",
            is_public=False,
            is_system=True,
            system_key=LIKED_SYSTEM_KEY,
        )
        session.add(playlist)
        await session.flush()
        logger.info("liked_playlist_created", user_id=str(user_id), playlist_id=str(playlist.id))
        return playlist

    async def is_track_liked(
        self,
        session: AsyncSession,
        user_id: UUID,
        provider: str,
        provider_track_id: str,
    ) -> bool:
        playlist = await self.ensure_liked_playlist(session, user_id)
        result = await session.execute(
            select(PlaylistItemModel.id)
            .join(SongModel, PlaylistItemModel.song_id == SongModel.id)
            .join(ProviderMappingModel, ProviderMappingModel.song_id == SongModel.id)
            .join(ProviderModel, ProviderMappingModel.provider_id == ProviderModel.id)
            .where(
                PlaylistItemModel.playlist_id == playlist.id,
                ProviderModel.name == provider,
                ProviderMappingModel.provider_track_id == provider_track_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def add_to_liked(
        self,
        session: AsyncSession,
        user_id: UUID,
        track: ProviderTrack,
    ) -> tuple[PlaylistItemModel, bool]:
        """Add track to Liked playlist. Returns (item, already_liked)."""
        playlist = await self.ensure_liked_playlist(session, user_id)
        song = await self.normalizer.resolve_canonical(track, session)

        existing = await session.execute(
            select(PlaylistItemModel).where(
                PlaylistItemModel.playlist_id == playlist.id,
                PlaylistItemModel.song_id == song.id,
            )
        )
        found = existing.scalar_one_or_none()
        if found:
            return found, True

        item = await self.add_track(session, user_id, playlist.id, track)
        return item, False

    async def get_user_playlist(
        self, session: AsyncSession, user_id: UUID, playlist_id: UUID
    ) -> PlaylistModel | None:
        result = await session.execute(
            select(PlaylistModel).where(
                PlaylistModel.id == playlist_id, PlaylistModel.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def get_all_playlist_song_ids(self, session: AsyncSession, user_id: UUID) -> set[UUID]:
        result = await session.execute(
            select(PlaylistItemModel.song_id)
            .join(PlaylistModel, PlaylistItemModel.playlist_id == PlaylistModel.id)
            .where(PlaylistModel.user_id == user_id)
        )
        return set(result.scalars().all())

    async def _song_to_track(
        self, session: AsyncSession, song_id: UUID, provider_name: str = "youtube"
    ) -> ProviderTrack | None:
        stmt = (
            select(SongModel, ArtistModel, ProviderMappingModel, ProviderModel)
            .join(ProviderMappingModel, ProviderMappingModel.song_id == SongModel.id)
            .join(ProviderModel, ProviderMappingModel.provider_id == ProviderModel.id)
            .outerjoin(ArtistModel, SongModel.artist_id == ArtistModel.id)
            .where(SongModel.id == song_id, ProviderModel.name == provider_name)
        )
        row = (await session.execute(stmt)).first()
        if not row:
            stmt_any = (
                select(SongModel, ArtistModel, ProviderMappingModel, ProviderModel)
                .join(ProviderMappingModel, ProviderMappingModel.song_id == SongModel.id)
                .join(ProviderModel, ProviderMappingModel.provider_id == ProviderModel.id)
                .outerjoin(ArtistModel, SongModel.artist_id == ArtistModel.id)
                .where(SongModel.id == song_id)
            )
            row = (await session.execute(stmt_any)).first()
        if not row:
            return None

        song, artist, mapping, provider = row
        return ProviderTrack(
            provider=provider.name,
            provider_track_id=mapping.provider_track_id,
            title=song.title,
            artist=artist.name if artist else "Unknown",
            album=None,
            duration_seconds=song.duration_seconds,
            thumbnail_url=mapping.thumbnail_url,
            canonical_song_id=song.id,
        )

    async def get_playlist_tracks(
        self, session: AsyncSession, user_id: UUID, playlist_id: UUID
    ) -> list[ProviderTrack]:
        playlist = await self.get_user_playlist(session, user_id, playlist_id)
        if not playlist:
            return []

        result = await session.execute(
            select(PlaylistItemModel)
            .where(PlaylistItemModel.playlist_id == playlist_id)
            .order_by(PlaylistItemModel.position)
        )
        items = result.scalars().all()
        tracks: list[ProviderTrack] = []
        for item in items:
            track = await self._song_to_track(session, item.song_id)
            if track:
                tracks.append(track)
        return tracks

    async def add_track(
        self,
        session: AsyncSession,
        user_id: UUID,
        playlist_id: UUID,
        track: ProviderTrack,
    ) -> PlaylistItemModel:
        playlist = await self.get_user_playlist(session, user_id, playlist_id)
        if not playlist:
            raise ValueError("Playlist not found")

        song = await self.normalizer.resolve_canonical(track, session)

        existing = await session.execute(
            select(PlaylistItemModel).where(
                PlaylistItemModel.playlist_id == playlist_id,
                PlaylistItemModel.song_id == song.id,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Song already in playlist")

        pos_result = await session.execute(
            select(func.coalesce(func.max(PlaylistItemModel.position), -1)).where(
                PlaylistItemModel.playlist_id == playlist_id
            )
        )
        next_pos = (pos_result.scalar() or -1) + 1

        item = PlaylistItemModel(
            playlist_id=playlist_id,
            song_id=song.id,
            position=next_pos,
        )
        session.add(item)
        await session.flush()
        logger.info("playlist_track_added", playlist_id=str(playlist_id), song_id=str(song.id))
        return item

    async def playlist_track_count(
        self, session: AsyncSession, playlist_id: UUID
    ) -> int:
        result = await session.execute(
            select(func.count())
            .select_from(PlaylistItemModel)
            .where(PlaylistItemModel.playlist_id == playlist_id)
        )
        return result.scalar() or 0
