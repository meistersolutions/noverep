from uuid import UUID

import random
import structlog
from dataclasses import dataclass
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.language_utils import (
    augment_search_query,
    random_lang_discovery_query,
    resolve_languages_from_prefs,
)
from app.application.services.memory_service import MemoryService
from app.application.services.recommendation_engine import RecommendationEngine
from app.application.services.song_matcher import is_same_song
from app.application.services.song_normalizer import SongNormalizer
from app.domain.entities import ProviderTrack
from app.infrastructure.database.models import (
    PlaylistItemModel,
    PlaylistModel,
    QueueItemModel,
    SongModel,
    UserPreferencesModel,
)

logger = structlog.get_logger()

TARGET_QUEUE_SIZE = 20


@dataclass
class QueueRefreshFilters:
    """Optional per-refresh overrides (fall back to saved preferences when unset)."""

    preferred_languages: list[str] | None = None
    year_from: int | None = None
    year_to: int | None = None
    skip_memory_filter: bool = False


class QueueService:
    """Intelligent queue – 20 upcoming songs seeded from the track now playing."""

    def __init__(
        self,
        recommendation_engine: RecommendationEngine,
        memory_service: MemoryService,
        normalizer: SongNormalizer,
    ):
        self.recommendation = recommendation_engine
        self.memory = memory_service
        self.normalizer = normalizer

    async def get_queue(self, session: AsyncSession, user_id: UUID) -> list[QueueItemModel]:
        result = await session.execute(
            select(QueueItemModel)
            .where(QueueItemModel.user_id == user_id)
            .order_by(QueueItemModel.position)
        )
        return list(result.scalars().all())

    def _user_languages(self, pref: UserPreferencesModel | None) -> list[str]:
        return resolve_languages_from_prefs(pref)

    def _search_seed_queries(self, seed: str, langs: list[str]) -> list[str]:
        q = seed.strip()
        if not q:
            return [self._build_seed_query(None)]
        return [
            augment_search_query(q, langs),
            augment_search_query(f"{q} songs", langs),
            augment_search_query(f"{q} official audio", langs),
        ]

    def _build_discovery_queries(
        self,
        pref: UserPreferencesModel | None,
        *,
        current: QueueItemModel | None = None,
        seed_query: str | None = None,
        from_preferences: bool = False,
        filters: QueueRefreshFilters | None = None,
    ) -> list[str]:
        langs = (
            filters.preferred_languages
            if filters and filters.preferred_languages
            else self._user_languages(pref)
        )

        if from_preferences:
            return [
                self._build_seed_query(pref, filters=filters),
                random_lang_discovery_query(random.choice(langs)),
                *self._year_queries(pref, filters=filters),
            ]

        active = (getattr(pref, "active_search_query", None) or "").strip() if pref else ""
        effective_seed = (seed_query or active or "").strip()
        if effective_seed:
            queries = self._search_seed_queries(effective_seed, langs)
            if current:
                queries.append(augment_search_query(f"{current.artist} {effective_seed}", langs))
            return queries

        if current:
            return [
                self._seed_from_track(current.artist, pref),
                augment_search_query(f"{current.artist} similar songs", langs),
                augment_search_query(self._build_seed_query(pref, filters=filters), langs),
                *self._year_queries(pref, current.artist, filters=filters),
                random_lang_discovery_query(langs[0] if len(langs) == 1 else random.choice(langs)),
            ]

        return [
            augment_search_query(self._build_seed_query(pref, filters=filters), langs),
            random_lang_discovery_query(langs[0] if len(langs) == 1 else random.choice(langs)),
        ]

    async def _persist_active_search(
        self,
        session: AsyncSession,
        pref: UserPreferencesModel | None,
        query: str | None,
    ) -> None:
        if not pref:
            return
        pref.active_search_query = query.strip() if query and query.strip() else None
        await session.flush()

    def _seed_from_track(self, artist: str, pref: UserPreferencesModel | None) -> str:
        langs = self._user_languages(pref)
        primary = langs[0] if len(langs) == 1 else random.choice(langs)
        return augment_search_query(artist, [primary])

    def _build_seed_query(
        self,
        pref: UserPreferencesModel | None,
        seed: str | None = None,
        artist: str | None = None,
        filters: QueueRefreshFilters | None = None,
    ) -> str:
        if seed:
            langs = (
                filters.preferred_languages
                if filters and filters.preferred_languages
                else self._user_languages(pref)
            )
            return augment_search_query(seed, langs)
        if artist:
            return self._seed_from_track(artist, pref)
        year_q = self._year_suffix(pref, filters)
        langs = (
            filters.preferred_languages
            if filters and filters.preferred_languages
            else self._user_languages(pref)
        )
        lang = random.choice(langs)
        return f"{random_lang_discovery_query(lang)}{year_q}"

    def _year_suffix(self, pref: UserPreferencesModel | None, filters: QueueRefreshFilters | None = None) -> str:
        y_from = (
            filters.year_from
            if filters and filters.year_from is not None
            else (getattr(pref, "discovery_year_from", None) if pref else None)
        )
        y_to = (
            filters.year_to
            if filters and filters.year_to is not None
            else (getattr(pref, "discovery_year_to", None) if pref else None)
        )
        if y_from and y_to:
            return f" {y_from} {y_to}"
        if y_from:
            return f" {y_from}"
        if y_to:
            return f" {y_to}"
        return ""

    def _year_queries(
        self,
        pref: UserPreferencesModel | None,
        artist: str | None = None,
        filters: QueueRefreshFilters | None = None,
    ) -> list[str]:
        y_from = (
            filters.year_from
            if filters and filters.year_from is not None
            else (getattr(pref, "discovery_year_from", None) if pref else None)
        )
        y_to = (
            filters.year_to
            if filters and filters.year_to is not None
            else (getattr(pref, "discovery_year_to", None) if pref else None)
        )
        if not y_from and not y_to:
            return []
        langs = (
            filters.preferred_languages
            if filters and filters.preferred_languages
            else self._user_languages(pref)
        )
        year_label = f"{y_from or ''}-{y_to or ''}".strip("-")
        queries = [augment_search_query(f"songs {year_label}", langs)]
        if artist:
            queries.append(augment_search_query(f"{artist} songs {year_label}", langs))
        if y_from and y_to:
            mid = (y_from + y_to) // 2
            queries.append(augment_search_query(f"best songs {mid}", langs))
        return queries

    async def _recent_context(self, session: AsyncSession, user_id: UUID) -> dict:
        from app.infrastructure.database.models import ListeningHistoryModel

        result = await session.execute(
            select(ListeningHistoryModel)
            .where(ListeningHistoryModel.user_id == user_id)
            .order_by(ListeningHistoryModel.played_at.desc())
            .limit(10)
        )
        entries = result.scalars().all()
        return {
            "artists": [e.artist_name for e in entries],
            "genres": [e.genre_name for e in entries if e.genre_name],
            "albums": [e.album_name for e in entries if e.album_name],
        }

    async def _queue_track_ids(self, queue: list[QueueItemModel]) -> set[str]:
        return {q.provider_track_id for q in queue}

    async def _queue_song_ids(self, queue: list[QueueItemModel]) -> set[UUID]:
        return {q.song_id for q in queue}

    async def _dedupe_queue(self, session: AsyncSession, queue: list[QueueItemModel]) -> list[QueueItemModel]:
        """Remove duplicate tracks/songs from queue, keeping the earliest row (and current)."""
        song_ids = {item.song_id for item in queue if item.song_id}
        mb_by_song: dict[UUID, str] = {}
        if song_ids:
            rows = await session.execute(
                select(SongModel.id, SongModel.musicbrainz_id).where(SongModel.id.in_(song_ids))
            )
            mb_by_song = {
                row[0]: row[1] for row in rows.all() if row[1]
            }

        seen_tracks: set[str] = set()
        seen_songs: set[UUID] = set()
        seen_mb: set[str] = set()
        kept: list[QueueItemModel] = []
        for item in sorted(queue, key=lambda q: (not q.is_current, q.position)):
            if item.provider_track_id in seen_tracks or item.song_id in seen_songs:
                await session.delete(item)
                continue
            mb_id = mb_by_song.get(item.song_id)
            if mb_id and mb_id in seen_mb:
                await session.delete(item)
                continue
            semantic_dup = next(
                (
                    existing
                    for existing in kept
                    if is_same_song(
                        item.title,
                        item.artist,
                        item.duration_seconds,
                        existing.title,
                        existing.artist,
                        existing.duration_seconds,
                    )
                ),
                None,
            )
            if semantic_dup:
                await session.delete(item)
                continue
            seen_tracks.add(item.provider_track_id)
            seen_songs.add(item.song_id)
            if mb_id:
                seen_mb.add(mb_id)
            kept.append(item)
        for i, item in enumerate(kept):
            item.position = i
        await session.flush()
        return kept

    async def _is_playlist_mode(self, session: AsyncSession, user_id: UUID) -> bool:
        pref = await self._get_prefs(session, user_id)
        return bool(pref and getattr(pref, "playback_mode", "discovery") == "playlist")

    async def _get_prefs(
        self, session: AsyncSession, user_id: UUID
    ) -> UserPreferencesModel | None:
        result = await session.execute(
            select(UserPreferencesModel).where(UserPreferencesModel.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def _playlist_song_ids(self, session: AsyncSession, user_id: UUID) -> set[UUID]:
        result = await session.execute(
            select(PlaylistItemModel.song_id)
            .join(PlaylistModel, PlaylistItemModel.playlist_id == PlaylistModel.id)
            .where(PlaylistModel.user_id == user_id)
        )
        return set(result.scalars().all())

    async def _set_playback_mode(
        self,
        session: AsyncSession,
        user_id: UUID,
        mode: str,
        playlist_id: UUID | None = None,
    ) -> None:
        pref = await self._get_prefs(session, user_id)
        if pref:
            pref.playback_mode = mode
            pref.active_playlist_id = playlist_id
            await session.flush()

    async def _recommend(
        self,
        session: AsyncSession,
        user_id: UUID,
        query: str,
        limit: int,
        recent: dict,
        extra_artists: list[str] | None = None,
        filters: QueueRefreshFilters | None = None,
    ):
        exclude = await self._playlist_song_ids(session, user_id)
        pref = await self._get_prefs(session, user_id)
        year_from = (
            filters.year_from
            if filters and filters.year_from is not None
            else (getattr(pref, "discovery_year_from", None) if pref else None)
        )
        year_to = (
            filters.year_to
            if filters and filters.year_to is not None
            else (getattr(pref, "discovery_year_to", None) if pref else None)
        )
        languages = (
            filters.preferred_languages
            if filters and filters.preferred_languages
            else self._user_languages(pref)
        )
        skip_memory = filters.skip_memory_filter if filters else False
        return await self.recommendation.recommend(
            session,
            user_id,
            query,
            limit=limit,
            recent_artists=(recent["artists"] + (extra_artists or [])),
            recent_genres=recent["genres"],
            recent_albums=recent["albums"],
            exclude_song_ids=exclude,
            year_from=year_from,
            year_to=year_to,
            preferred_languages=languages,
            skip_memory_filter=skip_memory,
        )

    async def sync_queue(
        self,
        session: AsyncSession,
        user_id: UUID,
        target_size: int = TARGET_QUEUE_SIZE,
    ) -> list[QueueItemModel]:
        """Keep queue at target_size: current song + upcoming recommendations from it."""
        if await self._is_playlist_mode(session, user_id):
            return await self.get_queue(session, user_id)

        queue = await self.get_queue(session, user_id)

        if not queue:
            return await self._fill_empty_queue(session, user_id, target_size)

        current_idx = next((i for i, q in enumerate(queue) if q.is_current), 0)

        # Drop already-played items before current
        for item in queue[:current_idx]:
            await session.delete(item)
        await session.flush()

        queue = await self.get_queue(session, user_id)
        if not queue:
            return await self._fill_empty_queue(session, user_id, target_size)

        current_idx = next((i for i, q in enumerate(queue) if q.is_current), 0)
        current = queue[current_idx]
        for i, item in enumerate(queue):
            item.position = i
            item.is_current = i == current_idx

        prefs_result = await session.execute(
            select(UserPreferencesModel).where(UserPreferencesModel.user_id == user_id)
        )
        pref = prefs_result.scalar_one_or_none()
        recent = await self._recent_context(session, user_id)

        queries = self._build_discovery_queries(pref, current=current)

        query_idx = 0
        attempts = 0
        max_attempts = target_size * 5

        while len(queue) < target_size and attempts < max_attempts:
            attempts += 1
            query = queries[query_idx % len(queries)]
            query_idx += 1

            candidates = await self._recommend(
                session,
                user_id,
                query,
                limit=15,
                recent=recent,
                extra_artists=[current.artist],
            )

            existing = await self._queue_track_ids(queue)
            existing_songs = await self._queue_song_ids(queue)
            added_any = False
            for candidate in candidates:
                if len(queue) >= target_size:
                    break
                if candidate.track.provider_track_id in existing:
                    continue
                if (
                    candidate.track.canonical_song_id
                    and candidate.track.canonical_song_id in existing_songs
                ):
                    continue
                try:
                    item = await self._append_track(
                        session, user_id, candidate.track, len(queue), is_current=False
                    )
                    queue.append(item)
                    existing.add(item.provider_track_id)
                    existing_songs.add(item.song_id)
                    added_any = True
                except ValueError:
                    continue
            if not added_any and query_idx >= len(queries) * 2:
                break

        await session.flush()
        queue = await self._dedupe_queue(session, queue)
        logger.info("queue_synced", user_id=str(user_id), size=len(queue))
        return queue

    async def refresh_upcoming(
        self,
        session: AsyncSession,
        user_id: UUID,
        *,
        seed_query: str | None = None,
        from_preferences: bool = False,
        target_size: int = TARGET_QUEUE_SIZE,
        filters: QueueRefreshFilters | None = None,
    ) -> list[QueueItemModel]:
        """Replace upcoming tracks; keep the song now playing. Seed from search or preferences."""
        if await self._is_playlist_mode(session, user_id):
            return await self.get_queue(session, user_id)

        queue = await self.get_queue(session, user_id)
        current: QueueItemModel | None = None

        if queue:
            current_idx = next((i for i, q in enumerate(queue) if q.is_current), 0)
            current = queue[current_idx]
            for item in queue:
                if item.id != current.id:
                    await session.delete(item)
            await session.flush()
            current.position = 0
            current.is_current = True

        prefs_result = await session.execute(
            select(UserPreferencesModel).where(UserPreferencesModel.user_id == user_id)
        )
        pref = prefs_result.scalar_one_or_none()
        recent = await self._recent_context(session, user_id)

        if from_preferences:
            await self._persist_active_search(session, pref, None)
        elif seed_query:
            await self._persist_active_search(session, pref, seed_query)

        queries = self._build_discovery_queries(
            pref,
            current=current,
            seed_query=seed_query,
            from_preferences=from_preferences,
            filters=filters,
        )

        queue = await self.get_queue(session, user_id)
        query_idx = 0
        attempts = 0
        max_attempts = target_size * 5
        seed_artists = recent["artists"] + ([current.artist] if current else [])

        while len(queue) < target_size and attempts < max_attempts:
            attempts += 1
            query = queries[query_idx % len(queries)]
            query_idx += 1

            candidates = await self._recommend(
                session, user_id, query, limit=15, recent=recent, extra_artists=seed_artists,
                filters=filters,
            )

            existing = await self._queue_track_ids(queue)
            existing_songs = await self._queue_song_ids(queue)
            added_any = False
            for candidate in candidates:
                if len(queue) >= target_size:
                    break
                if candidate.track.provider_track_id in existing:
                    continue
                if (
                    candidate.track.canonical_song_id
                    and candidate.track.canonical_song_id in existing_songs
                ):
                    continue
                try:
                    is_first = len(queue) == 0
                    item = await self._append_track(
                        session,
                        user_id,
                        candidate.track,
                        len(queue),
                        is_current=is_first,
                    )
                    queue.append(item)
                    existing.add(item.provider_track_id)
                    existing_songs.add(item.song_id)
                    added_any = True
                except ValueError:
                    continue
            if not added_any and query_idx >= len(queries) * 2:
                break

        if queue and not any(q.is_current for q in queue):
            queue[0].is_current = True

        await session.flush()
        queue = await self._dedupe_queue(session, queue)
        source = (
            "preferences"
            if from_preferences
            else ("search" if seed_query or (pref and pref.active_search_query) else "current")
        )
        logger.info("queue_refreshed", user_id=str(user_id), size=len(queue), source=source)
        return queue

    async def _fill_empty_queue(
        self, session: AsyncSession, user_id: UUID, target_size: int
    ) -> list[QueueItemModel]:
        prefs_result = await session.execute(
            select(UserPreferencesModel).where(UserPreferencesModel.user_id == user_id)
        )
        pref = prefs_result.scalar_one_or_none()
        recent = await self._recent_context(session, user_id)
        queue: list[QueueItemModel] = []
        queries = self._build_discovery_queries(pref)
        query_idx = 0
        attempts = 0
        max_attempts = target_size * 5

        while len(queue) < target_size and attempts < max_attempts:
            attempts += 1
            query = queries[query_idx % len(queries)]
            query_idx += 1
            candidates = await self._recommend(
                session, user_id, query, limit=15, recent=recent
            )
            existing = await self._queue_track_ids(queue)
            existing_songs = await self._queue_song_ids(queue)
            for candidate in candidates:
                if len(queue) >= target_size:
                    break
                if candidate.track.provider_track_id in existing:
                    continue
                if (
                    candidate.track.canonical_song_id
                    and candidate.track.canonical_song_id in existing_songs
                ):
                    continue
                try:
                    is_first = len(queue) == 0
                    item = await self._append_track(
                        session,
                        user_id,
                        candidate.track,
                        len(queue),
                        is_current=is_first,
                    )
                    queue.append(item)
                    existing.add(item.provider_track_id)
                    existing_songs.add(item.song_id)
                except ValueError:
                    continue
        queue = await self._dedupe_queue(session, queue)
        return queue

    async def _append_track(
        self,
        session: AsyncSession,
        user_id: UUID,
        track: ProviderTrack,
        position: int,
        is_current: bool,
        explicitly_requested: bool = False,
    ) -> QueueItemModel:
        song = await self.normalizer.resolve_canonical(track, session)
        if not explicitly_requested:
            allowed = await self.memory.is_repeat_allowed(session, user_id, song.id)
            if not allowed:
                raise ValueError("Song recently played")

        item = QueueItemModel(
            user_id=user_id,
            song_id=song.id,
            provider=track.provider,
            provider_track_id=track.provider_track_id,
            title=track.title,
            artist=track.artist,
            album=track.album,
            thumbnail_url=track.thumbnail_url,
            duration_seconds=track.duration_seconds,
            position=position,
            is_current=is_current,
        )
        session.add(item)
        await session.flush()
        return item

    async def add_to_queue(
        self,
        session: AsyncSession,
        user_id: UUID,
        track: ProviderTrack,
        explicitly_requested: bool = False,
        play_now: bool = False,
    ) -> QueueItemModel:
        if play_now:
            await self._set_playback_mode(session, user_id, "discovery", None)
            await session.execute(delete(QueueItemModel).where(QueueItemModel.user_id == user_id))
            await session.flush()
            item = await self._append_track(
                session, user_id, track, 0, is_current=True, explicitly_requested=explicitly_requested
            )
            await self.sync_queue(session, user_id)
            refreshed = await self.get_queue(session, user_id)
            for q in refreshed:
                if q.provider_track_id == track.provider_track_id:
                    q.is_current = True
                    return q
            return item

        return await self._append_track(
            session,
            user_id,
            track,
            len(await self.get_queue(session, user_id)),
            is_current=False,
            explicitly_requested=explicitly_requested,
        )

    async def insert_play_next(
        self,
        session: AsyncSession,
        user_id: UUID,
        track: ProviderTrack,
        explicitly_requested: bool = False,
    ) -> QueueItemModel:
        """Insert track immediately after the currently playing song."""
        queue = await self.get_queue(session, user_id)
        current_idx = next((i for i, q in enumerate(queue) if q.is_current), -1)
        insert_pos = current_idx + 1 if current_idx >= 0 else 0

        existing_ids = await self._queue_track_ids(queue)
        if track.provider_track_id in existing_ids:
            for q in queue:
                if q.provider_track_id == track.provider_track_id:
                    if q.position != insert_pos:
                        await self._move_to_position(queue, q, insert_pos)
                        await session.flush()
                    return q

        for q in queue:
            if q.position >= insert_pos:
                q.position += 1

        item = await self._append_track(
            session,
            user_id,
            track,
            insert_pos,
            is_current=False,
            explicitly_requested=explicitly_requested,
        )
        await session.flush()
        return item

    async def _move_to_position(
        self, queue: list[QueueItemModel], item: QueueItemModel, new_pos: int
    ) -> None:
        old_pos = item.position
        if old_pos == new_pos:
            return
        if old_pos < new_pos:
            for q in queue:
                if q.id != item.id and old_pos < q.position <= new_pos:
                    q.position -= 1
        else:
            for q in queue:
                if q.id != item.id and new_pos <= q.position < old_pos:
                    q.position += 1
        item.position = new_pos

    async def next_track(
        self,
        session: AsyncSession,
        user_id: UUID,
        seed_query: str | None = None,
        *,
        defer_sync: bool = False,
    ) -> QueueItemModel | None:
        queue = await self.get_queue(session, user_id)
        if not queue:
            filled = await self._fill_empty_queue(session, user_id, TARGET_QUEUE_SIZE)
            return filled[0] if filled else None

        current_idx = next((i for i, q in enumerate(queue) if q.is_current), 0)
        next_provider_id = None
        if current_idx + 1 < len(queue):
            next_provider_id = queue[current_idx + 1].provider_track_id

        await session.delete(queue[current_idx])
        await session.flush()

        queue = await self.get_queue(session, user_id)
        if not queue:
            filled = await self._fill_empty_queue(session, user_id, TARGET_QUEUE_SIZE)
            return filled[0] if filled else None

        new_current_idx = 0
        if next_provider_id:
            for i, q in enumerate(queue):
                if q.provider_track_id == next_provider_id:
                    new_current_idx = i
                    break

        for i, q in enumerate(queue):
            q.position = i
            q.is_current = i == new_current_idx

        await session.flush()
        current_item = queue[new_current_idx]

        queue = await self._dedupe_queue(session, queue)
        current_item = next((q for q in queue if q.is_current), current_item)

        if defer_sync:
            return current_item

        if not await self._is_playlist_mode(session, user_id):
            await self.sync_queue(session, user_id)

        refreshed = await self.get_queue(session, user_id)
        for q in refreshed:
            if q.provider_track_id == current_item.provider_track_id:
                for x in refreshed:
                    x.is_current = False
                q.is_current = True
                return q
        if refreshed:
            for x in refreshed:
                x.is_current = False
            refreshed[0].is_current = True
            return refreshed[0]
        return None

    async def previous_track(
        self, session: AsyncSession, user_id: UUID
    ) -> QueueItemModel | None:
        queue = await self.get_queue(session, user_id)
        current_idx = next((i for i, q in enumerate(queue) if q.is_current), 0)
        if current_idx > 0:
            queue[current_idx].is_current = False
            queue[current_idx - 1].is_current = True
            await session.flush()
            return queue[current_idx - 1]
        await session.flush()
        return queue[0] if queue else None

    async def ensure_queue_size(
        self, session: AsyncSession, user_id: UUID, minimum: int = TARGET_QUEUE_SIZE
    ) -> list[QueueItemModel]:
        return await self.sync_queue(session, user_id, target_size=minimum)

    async def clear_queue(self, session: AsyncSession, user_id: UUID) -> None:
        await session.execute(delete(QueueItemModel).where(QueueItemModel.user_id == user_id))

    async def play_queue_item(
        self, session: AsyncSession, user_id: UUID, item_id: UUID
    ) -> QueueItemModel | None:
        queue = await self.get_queue(session, user_id)
        target_idx = next((i for i, q in enumerate(queue) if q.id == item_id), -1)
        if target_idx < 0:
            return None
        target = queue[target_idx]

        reordered = [target] + [q for q in queue if q.id != item_id]
        for i, q in enumerate(reordered):
            q.position = i
            q.is_current = i == 0
        await session.flush()

        if not await self._is_playlist_mode(session, user_id):
            await self.sync_queue(session, user_id)

        refreshed = await self.get_queue(session, user_id)
        for q in refreshed:
            if q.provider_track_id == target.provider_track_id:
                for x in refreshed:
                    x.is_current = False
                q.is_current = True
                return q
        return reordered[0] if reordered else None

    async def load_playlist_queue(
        self,
        session: AsyncSession,
        user_id: UUID,
        playlist_id: UUID,
        tracks: list[ProviderTrack],
        start_index: int = 0,
    ) -> list[QueueItemModel]:
        if not tracks:
            return []

        await session.execute(delete(QueueItemModel).where(QueueItemModel.user_id == user_id))
        await session.flush()
        await self._set_playback_mode(session, user_id, "playlist", playlist_id)

        queue: list[QueueItemModel] = []
        for i, track in enumerate(tracks):
            item = await self._append_track(
                session,
                user_id,
                track,
                i,
                is_current=(i == start_index),
                explicitly_requested=True,
            )
            queue.append(item)

        await session.flush()
        logger.info(
            "playlist_queue_loaded",
            user_id=str(user_id),
            playlist_id=str(playlist_id),
            size=len(queue),
        )
        return queue
