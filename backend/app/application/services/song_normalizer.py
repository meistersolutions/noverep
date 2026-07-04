from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.song_matcher import (
    extract_core_title,
    is_same_song,
    match_score,
    normalize_text as semantic_normalize_text,
    token_set,
)
from app.domain.entities import ProviderTrack
from app.domain.interfaces import SongNormalizerPort
from app.infrastructure.database.models import (
    ArtistModel,
    ProviderMappingModel,
    ProviderModel,
    SongModel,
)
from app.infrastructure.providers.youtube.metadata_utils import (
    is_placeholder_youtube_title,
    pick_display_artist,
    pick_display_title,
)


def _normalize_text(text: str) -> str:
    return semantic_normalize_text(text)


class SongNormalizer(SongNormalizerPort):
    """Maps provider tracks to canonical songs via normalized + semantic keys."""

    DURATION_TOLERANCE = 5  # seconds
    SEMANTIC_MATCH_THRESHOLD = 0.82

    def normalize_key(self, title: str, artist: str, duration_seconds: int | None) -> str:
        core_title = extract_core_title(title, artist)
        base = f"{_normalize_text(artist)}|{_normalize_text(core_title)}"
        if duration_seconds:
            bucket = duration_seconds // self.DURATION_TOLERANCE
            base = f"{base}|{bucket}"
        return sha256(base.encode()).hexdigest()[:32]

    async def resolve_canonical(self, track: ProviderTrack, session: AsyncSession) -> SongModel:
        song = await self._find_by_provider_track(session, track)
        if song:
            await self._upgrade_song_metadata(session, song, track)
            await self._ensure_provider_mapping(session, song, track)
            return song

        norm_key = self.normalize_key(track.title, track.artist, track.duration_seconds)

        result = await session.execute(select(SongModel).where(SongModel.normalization_key == norm_key))
        song = result.scalar_one_or_none()

        if song:
            await self._upgrade_song_metadata(session, song, track)
            await self._ensure_provider_mapping(session, song, track)
            return song

        song = await self._find_semantic_match(session, track)
        if song:
            await self._upgrade_song_metadata(session, song, track)
            await self._ensure_provider_mapping(session, song, track)
            return song

        artist_result = await session.execute(
            select(ArtistModel).where(ArtistModel.normalized_name == _normalize_text(track.artist))
        )
        artist = artist_result.scalar_one_or_none()
        if not artist:
            artist = ArtistModel(name=track.artist, normalized_name=_normalize_text(track.artist))
            session.add(artist)
            await session.flush()

        song = SongModel(
            title=track.title,
            normalized_title=_normalize_text(extract_core_title(track.title, track.artist)),
            artist_id=artist.id,
            duration_seconds=track.duration_seconds,
            language=track.language,
            release_year=track.release_year,
            isrc=track.isrc,
            normalization_key=norm_key,
            popularity=track.popularity,
        )
        session.add(song)
        await session.flush()
        await self._ensure_provider_mapping(session, song, track)
        return song

    async def _find_by_provider_track(
        self, session: AsyncSession, track: ProviderTrack
    ) -> SongModel | None:
        result = await session.execute(
            select(SongModel)
            .join(ProviderMappingModel, ProviderMappingModel.song_id == SongModel.id)
            .join(ProviderModel, ProviderModel.id == ProviderMappingModel.provider_id)
            .where(
                ProviderModel.name == track.provider,
                ProviderMappingModel.provider_track_id == track.provider_track_id,
            )
        )
        return result.scalar_one_or_none()

    async def _find_semantic_match(
        self, session: AsyncSession, track: ProviderTrack
    ) -> SongModel | None:
        core_title = extract_core_title(track.title, track.artist)
        title_tokens = sorted(token_set(core_title), key=len, reverse=True)
        artist_tokens = sorted(token_set(track.artist), key=len, reverse=True)

        candidates: dict[UUID, SongModel] = {}

        for token in title_tokens[:4]:
            if len(token) < 3:
                continue
            result = await session.execute(
                select(SongModel).where(SongModel.normalized_title.contains(token)).limit(50)
            )
            for song in result.scalars():
                candidates[song.id] = song

        for token in artist_tokens[:3]:
            if len(token) < 3:
                continue
            artists = await session.execute(
                select(ArtistModel).where(ArtistModel.normalized_name.contains(token)).limit(15)
            )
            for artist in artists.scalars():
                songs = await session.execute(
                    select(SongModel).where(SongModel.artist_id == artist.id).limit(50)
                )
                for song in songs.scalars():
                    candidates[song.id] = song

        if not candidates:
            return None

        artist_ids = {song.artist_id for song in candidates.values() if song.artist_id}
        artist_names: dict[UUID, str] = {}
        if artist_ids:
            rows = await session.execute(select(ArtistModel).where(ArtistModel.id.in_(artist_ids)))
            for artist in rows.scalars():
                artist_names[artist.id] = artist.name

        best: SongModel | None = None
        best_score = 0.0
        for song in candidates.values():
            song_artist = artist_names.get(song.artist_id, "") if song.artist_id else ""
            score = match_score(
                track.title,
                track.artist,
                track.duration_seconds,
                song.title,
                song_artist,
                song.duration_seconds,
            )
            if score >= self.SEMANTIC_MATCH_THRESHOLD and score > best_score:
                if is_same_song(
                    track.title,
                    track.artist,
                    track.duration_seconds,
                    song.title,
                    song_artist,
                    song.duration_seconds,
                    threshold=self.SEMANTIC_MATCH_THRESHOLD,
                ):
                    best_score = score
                    best = song
        return best

    async def _upgrade_song_metadata(
        self, session: AsyncSession, song: SongModel, track: ProviderTrack
    ) -> None:
        new_title = pick_display_title(track.title, song.title)
        if new_title != song.title and (
            is_placeholder_youtube_title(song.title) or not is_placeholder_youtube_title(new_title)
        ):
            song.title = new_title
            song.normalized_title = _normalize_text(new_title)

        artist_result = await session.execute(select(ArtistModel).where(ArtistModel.id == song.artist_id))
        artist = artist_result.scalar_one()
        new_artist = pick_display_artist(track.artist, artist.name)
        if new_artist != artist.name and (
            artist.name.lower() in ("unknown", "unknown artist")
            or is_placeholder_youtube_title(artist.name)
        ):
            artist.name = new_artist
            artist.normalized_name = _normalize_text(new_artist)

    async def _ensure_provider_mapping(
        self, session: AsyncSession, song: SongModel, track: ProviderTrack
    ) -> None:
        provider_result = await session.execute(
            select(ProviderModel).where(ProviderModel.name == track.provider)
        )
        provider = provider_result.scalar_one_or_none()
        if not provider:
            provider = ProviderModel(name=track.provider, display_name=track.provider.title())
            session.add(provider)
            await session.flush()

        mapping_result = await session.execute(
            select(ProviderMappingModel).where(
                ProviderMappingModel.provider_id == provider.id,
                ProviderMappingModel.provider_track_id == track.provider_track_id,
            )
        )
        mapping = mapping_result.scalar_one_or_none()
        if not mapping:
            session.add(
                ProviderMappingModel(
                    song_id=song.id,
                    provider_id=provider.id,
                    provider_track_id=track.provider_track_id,
                    thumbnail_url=track.thumbnail_url,
                )
            )
        elif track.thumbnail_url and not mapping.thumbnail_url:
            mapping.thumbnail_url = track.thumbnail_url
