from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING
from uuid import UUID

import asyncio
import random
import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.language_utils import (
    augment_search_query,
    random_lang_discovery_query,
    resolve_languages_from_prefs,
)
from app.application.services.library_hash import library_content_hash
from app.application.services.memory_service import HeardSongSnapshot, MemoryService
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

if TYPE_CHECKING:
    from app.application.services.home_recommendations import HomeRecommendationService
    from app.infrastructure.external.songs_library_client import SongsLibraryClient

logger = structlog.get_logger()

TARGET_QUEUE_SIZE = 20
QUEUE_SYNC_TIMEOUT_SEC = 55.0
MAX_ACTIVE_SEEDS = 5
LIBRARY_POOL_LOW = 30
# How many upcoming library tracks to pre-resolve YouTube ids for (beyond mapped).
LIBRARY_RESOLVE_AHEAD = 20


@dataclass
class QueueRefreshFilters:
    """Optional per-refresh overrides (fall back to saved preferences when unset)."""

    preferred_languages: list[str] | None = None
    year_from: int | None = None
    year_to: int | None = None
    popularity_min: float | None = None
    popularity_max: float | None = None
    skip_memory_filter: bool = False


@dataclass
class RemoveQueueResult:
    was_current: bool
    next_item: QueueItemModel | None
    queue: list[QueueItemModel]


class QueueService:
    """Intelligent queue – 20 upcoming songs seeded from the track now playing."""

    def __init__(
        self,
        recommendation_engine: RecommendationEngine,
        memory_service: MemoryService,
        normalizer: SongNormalizer,
        home_recommendations: "HomeRecommendationService | None" = None,
        songs_library: "SongsLibraryClient | None" = None,
    ):
        self.recommendation = recommendation_engine
        self.memory = memory_service
        self.normalizer = normalizer
        self.home = home_recommendations
        self.songs_library = songs_library

    async def get_queue(self, session: AsyncSession, user_id: UUID) -> list[QueueItemModel]:
        result = await session.execute(
            select(QueueItemModel)
            .where(QueueItemModel.user_id == user_id)
            .order_by(QueueItemModel.position)
        )
        return list(result.scalars().all())

    @staticmethod
    def _normalize_seeds(seeds: list[str] | None) -> list[str]:
        if not seeds:
            return []
        seen: set[str] = set()
        out: list[str] = []
        for raw in seeds:
            if not isinstance(raw, str):
                continue
            q = raw.strip()
            if not q:
                continue
            key = q.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(q)
            if len(out) >= MAX_ACTIVE_SEEDS:
                break
        return out

    def _active_seeds(self, pref: UserPreferencesModel | None) -> list[str]:
        if not pref:
            return []
        from_list = self._normalize_seeds(getattr(pref, "active_search_queries", None) or [])
        if from_list:
            return from_list
        single = (getattr(pref, "active_search_query", None) or "").strip()
        return [single] if single else []

    def _user_languages(self, pref: UserPreferencesModel | None) -> list[str]:
        return resolve_languages_from_prefs(pref)

    def _youtube_discovery_enabled(self, pref: UserPreferencesModel | None) -> bool:
        if pref is None:
            return True
        return bool(getattr(pref, "discovery_youtube_enabled", True))

    def _search_seed_queries(self, seed: str, langs: list[str]) -> list[str]:
        q = seed.strip()
        if not q:
            return [self._build_seed_query(None)]
        return [
            augment_search_query(q, langs),
            augment_search_query(f"{q} songs", langs),
            augment_search_query(f"{q} official audio", langs),
        ]

    def _interleave_seed_queries(
        self,
        seeds: list[str],
        langs: list[str],
        *,
        current: QueueItemModel | None = None,
    ) -> list[str]:
        """Round-robin query variants across seeds so the queue mixes niches."""
        per_seed = [self._search_seed_queries(seed, langs) for seed in seeds]
        queries: list[str] = []
        max_len = max((len(qs) for qs in per_seed), default=0)
        for i in range(max_len):
            for seed_qs in per_seed:
                if i < len(seed_qs):
                    queries.append(seed_qs[i])
        if current:
            for seed in seeds[:3]:
                queries.append(augment_search_query(f"{current.artist} {seed}", langs))
        # Escape hatch so refill cannot paint itself into a single-niche corner.
        lang = langs[0] if len(langs) == 1 else random.choice(langs)
        queries.append(random_lang_discovery_query(lang))
        return queries

    def _build_discovery_queries(
        self,
        pref: UserPreferencesModel | None,
        *,
        current: QueueItemModel | None = None,
        seed_query: str | None = None,
        seed_queries: list[str] | None = None,
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

        seeds = self._normalize_seeds(seed_queries)
        if not seeds and seed_query and seed_query.strip():
            seeds = self._normalize_seeds([seed_query])
        if not seeds:
            seeds = self._active_seeds(pref)
        if seeds:
            return self._interleave_seed_queries(seeds, langs, current=current)

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

    async def _persist_active_seeds(
        self,
        session: AsyncSession,
        pref: UserPreferencesModel | None,
        seeds: list[str] | None,
    ) -> None:
        if not pref:
            return
        cleaned = self._normalize_seeds(seeds)
        pref.active_search_queries = cleaned
        # Keep legacy single field in sync for older clients.
        pref.active_search_query = cleaned[0] if cleaned else None
        await session.flush()

    async def _persist_active_search(
        self,
        session: AsyncSession,
        pref: UserPreferencesModel | None,
        query: str | None,
    ) -> None:
        """Back-compat wrapper: persist a single seed as a one-item list."""
        await self._persist_active_seeds(
            session, pref, [query] if query and query.strip() else []
        )

    @staticmethod
    def _track_response_to_provider(track) -> ProviderTrack:
        return ProviderTrack(
            provider=track.provider,
            provider_track_id=track.provider_track_id,
            title=track.title,
            artist=track.artist,
            album=track.album,
            duration_seconds=track.duration_seconds,
            thumbnail_url=track.thumbnail_url,
            canonical_song_id=getattr(track, "canonical_song_id", None),
            popularity=float(getattr(track, "score", 0) or 0),
        )

    async def _append_home_discovery(
        self,
        session: AsyncSession,
        user_id: UUID,
        queue: list[QueueItemModel],
        target_size: int,
    ) -> list[QueueItemModel]:
        """Fill remaining slots from the same discovery pool as the home screen."""
        if not self.home or len(queue) >= target_size:
            return queue

        try:
            sections = await self.home.get_home_sections(session, user_id)
        except Exception as e:
            logger.warning("home_discovery_fallback_failed", user_id=str(user_id), error=str(e))
            return queue

        tracks = []
        for section in sections:
            for track in section.get("tracks") or []:
                tracks.append(track)
        if not tracks:
            return queue

        random.shuffle(tracks)
        existing = await self._queue_track_ids(queue)
        existing_songs = await self._queue_song_ids(queue)
        blocked_songs = await self.memory.get_blocked_song_ids(session, user_id)
        added = 0

        for track in tracks:
            if len(queue) >= target_size:
                break
            provider_track = self._track_response_to_provider(track)
            candidate = SimpleNamespace(track=provider_track)
            if self._skip_recommendation_candidate(
                candidate, existing, existing_songs, blocked_songs
            ):
                continue
            try:
                is_first = len(queue) == 0
                item = await self._append_track(
                    session,
                    user_id,
                    provider_track,
                    len(queue),
                    is_current=is_first,
                )
                queue.append(item)
                existing.add(item.provider_track_id)
                existing_songs.add(item.song_id)
                added += 1
            except ValueError:
                continue

        if added:
            logger.info(
                "queue_filled_from_home",
                user_id=str(user_id),
                added=added,
                size=len(queue),
            )
        return queue

    @staticmethod
    def _provider_track_from_library(lib_song) -> ProviderTrack | None:
        """Build a ProviderTrack only when a YouTube video id is already known."""
        video_id = getattr(lib_song, "youtube_video_id", None)
        if not video_id:
            return None
        artist = (
            (lib_song.singers[0] if lib_song.singers else None)
            or lib_song.composer_name
            or "Unknown Artist"
        )
        return ProviderTrack(
            provider="youtube",
            provider_track_id=video_id,
            title=lib_song.song_name,
            artist=artist,
            album=lib_song.movie_name,
            duration_seconds=None,
            thumbnail_url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            release_year=lib_song.release_year,
            popularity=float(lib_song.popularity or 0) / 100.0,
        )

    async def _ensure_library_youtube_ids(self, lib_songs: list, *, need: int) -> list:
        """Prefer mapped songs; batch-resolve missing YouTube ids before enqueue.

        Songs that still lack a video id after resolve are dropped (never queued).
        """
        if not lib_songs:
            return []
        mapped = [s for s in lib_songs if getattr(s, "youtube_video_id", None)]
        unmapped = [s for s in lib_songs if not getattr(s, "youtube_video_id", None)]
        # Resolve enough unmapped tracks to cover remaining queue slots (+ small buffer).
        resolve_budget = max(0, min(len(unmapped), max(need, LIBRARY_RESOLVE_AHEAD) - len(mapped)))
        to_resolve = unmapped[:resolve_budget]
        if to_resolve and self.songs_library and self.songs_library.enabled:
            resolved_map = await self.songs_library.resolve_youtube_many(
                [s.id for s in to_resolve]
            )
            for song in to_resolve:
                resolved = resolved_map.get(song.id)
                if resolved and resolved.youtube_video_id:
                    mapped.append(resolved)
                # else: skip — do not enqueue without a video id
            skipped = len(to_resolve) - sum(1 for s in to_resolve if s.id in resolved_map)
            if skipped:
                logger.info(
                    "library_youtube_resolve_skipped",
                    attempted=len(to_resolve),
                    resolved=len(to_resolve) - skipped,
                    skipped=skipped,
                )
        # Mapped first so already-known ids play immediately; newly resolved follow.
        return mapped

    def _library_exclude_hashes(self, heard_snapshots: list[HeardSongSnapshot]) -> list[str]:
        """Approximate library content hashes for heard songs (never-repeat hint)."""
        hashes: list[str] = []
        for snap in heard_snapshots:
            hashes.append(
                library_content_hash(
                    snap.title,
                    None,
                    snap.artist,
                    None,
                )
            )
        return hashes

    async def _append_from_songs_library(
        self,
        session: AsyncSession,
        user_id: UUID,
        queue: list[QueueItemModel],
        target_size: int,
        *,
        pref: UserPreferencesModel | None = None,
        seeds: list[str] | None = None,
        filters: QueueRefreshFilters | None = None,
        recent: dict | None = None,
    ) -> list[QueueItemModel]:
        """Fill queue slots from the standalone Songs Library catalog.

        Every enqueued library track must already have a YouTube video id.
        Prefers mapped catalog rows; batch-resolves a window of unmapped songs
        before returning. Unresolvable songs are skipped (not left empty).
        """
        if not self.songs_library or not self.songs_library.enabled:
            return queue
        if len(queue) >= target_size:
            return queue

        active = self._normalize_seeds(seeds) or self._active_seeds(pref)
        composers = active if active else [None]

        existing = await self._queue_track_ids(queue)
        existing_songs = await self._queue_song_ids(queue)
        blocked_songs = await self.memory.get_blocked_song_ids(session, user_id)
        heard_snapshots = await self.memory.get_heard_song_snapshots(session, user_id)
        exclude_hashes = self._library_exclude_hashes(heard_snapshots)
        year_from = filters.year_from if filters else None
        year_to = filters.year_to if filters else None
        popularity_min = filters.popularity_min if filters else None
        popularity_max = filters.popularity_max if filters else None
        languages = (
            filters.preferred_languages
            if filters and filters.preferred_languages
            else self._user_languages(pref)
        )
        # "all" / empty means no language restriction on the catalog sample.
        lang_filter = [
            lang for lang in (languages or []) if lang and lang.casefold() != "all"
        ] or None
        added = 0

        for composer in composers:
            if len(queue) >= target_size:
                break
            need = target_size - len(queue)
            pool_limit = max(need * 2, LIBRARY_POOL_LOW)

            # Fast path: already-mapped songs (youtube_video_id present).
            mapped = await self.songs_library.sample(
                composer=composer,
                seed=composer,
                year_from=year_from,
                year_to=year_to,
                popularity_min=popularity_min,
                popularity_max=popularity_max,
                languages=lang_filter,
                exclude_hashes=exclude_hashes,
                only_mapped=True,
                limit=pool_limit,
            )
            lib_songs = list(mapped)

            # Top up with unmapped + parallel resolve when mapped pool is thin.
            if len(lib_songs) < need:
                exclude_ids = [s.id for s in lib_songs if s.id]
                unmapped_pool = await self.songs_library.sample(
                    composer=composer,
                    seed=composer,
                    year_from=year_from,
                    year_to=year_to,
                    popularity_min=popularity_min,
                    popularity_max=popularity_max,
                    languages=lang_filter,
                    exclude_hashes=exclude_hashes,
                    exclude_ids=exclude_ids,
                    only_mapped=False,
                    limit=pool_limit,
                )
                # Prefer rows that somehow already have an id; resolve the rest.
                lib_songs = await self._ensure_library_youtube_ids(
                    lib_songs + unmapped_pool,
                    need=need,
                )

            if len(lib_songs) < LIBRARY_POOL_LOW and composer:
                # Catalog thin for this seed — queue continuous discovery (best-effort).
                await self.songs_library.discover([composer])
                more_mapped = await self.songs_library.sample(
                    composer=composer,
                    seed=composer,
                    year_from=year_from,
                    year_to=year_to,
                    popularity_min=popularity_min,
                    popularity_max=popularity_max,
                    languages=lang_filter,
                    exclude_hashes=exclude_hashes,
                    exclude_ids=[s.id for s in lib_songs if s.id],
                    only_mapped=True,
                    limit=pool_limit,
                )
                if more_mapped:
                    lib_songs = await self._ensure_library_youtube_ids(
                        lib_songs + more_mapped,
                        need=need,
                    )
                elif len(lib_songs) < need:
                    more = await self.songs_library.sample(
                        composer=composer,
                        seed=composer,
                        year_from=year_from,
                        year_to=year_to,
                        popularity_min=popularity_min,
                        popularity_max=popularity_max,
                        languages=lang_filter,
                        exclude_hashes=exclude_hashes,
                        exclude_ids=[s.id for s in lib_songs if s.id],
                        only_mapped=False,
                        limit=pool_limit,
                    )
                    lib_songs = await self._ensure_library_youtube_ids(
                        lib_songs + more,
                        need=need,
                    )

            for lib_song in lib_songs:
                if len(queue) >= target_size:
                    break
                track = self._provider_track_from_library(lib_song)
                if not track:
                    continue
                candidate = SimpleNamespace(track=track)
                if self._skip_recommendation_candidate(
                    candidate, existing, existing_songs, blocked_songs
                ):
                    continue
                try:
                    is_first = len(queue) == 0
                    item = await self._append_track(
                        session,
                        user_id,
                        track,
                        len(queue),
                        is_current=is_first,
                    )
                    queue.append(item)
                    existing.add(item.provider_track_id)
                    existing_songs.add(item.song_id)
                    added += 1
                except ValueError:
                    continue

        if added:
            logger.info(
                "queue_filled_from_songs_library",
                user_id=str(user_id),
                added=added,
                size=len(queue),
                seeds=active,
            )
        return queue

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

    def _skip_recommendation_candidate(
        self,
        candidate,
        existing_tracks: set[str],
        existing_songs: set[UUID],
        blocked_songs: set[UUID],
    ) -> bool:
        if candidate.track.provider_track_id in existing_tracks:
            return True
        canonical_id = candidate.track.canonical_song_id
        return bool(
            canonical_id and (canonical_id in existing_songs or canonical_id in blocked_songs)
        )

    def _is_heard_queue_item(
        self,
        item: QueueItemModel,
        blocked_song_ids: set[UUID],
        heard_snapshots: list[HeardSongSnapshot],
    ) -> bool:
        if item.song_id and item.song_id in blocked_song_ids:
            return True
        return any(
            is_same_song(
                item.title,
                item.artist,
                item.duration_seconds,
                heard.title,
                heard.artist,
                heard.duration_seconds,
            )
            for heard in heard_snapshots
        )

    async def _purge_heard_from_queue(
        self, session: AsyncSession, user_id: UUID
    ) -> list[QueueItemModel]:
        """Remove upcoming queue items already heard on any device (memory window)."""
        if await self._is_playlist_mode(session, user_id):
            return await self.get_queue(session, user_id)

        queue = await self.get_queue(session, user_id)
        if not queue:
            return queue

        blocked_song_ids = await self.memory.get_blocked_song_ids(session, user_id)
        heard_snapshots = await self.memory.get_heard_song_snapshots(session, user_id)
        if not blocked_song_ids and not heard_snapshots:
            return queue

        removed = 0
        for item in queue:
            if item.is_current:
                continue
            if not self._is_heard_queue_item(item, blocked_song_ids, heard_snapshots):
                continue
            await session.delete(item)
            removed += 1

        if not removed:
            return queue

        await session.flush()
        queue = await self.get_queue(session, user_id)
        if queue and not any(q.is_current for q in queue):
            for i, q in enumerate(queue):
                q.position = i
                q.is_current = i == 0
            await session.flush()
            queue = await self.get_queue(session, user_id)

        logger.info("queue_purged_heard", user_id=str(user_id), removed=removed)
        return queue

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

        try:
            return await asyncio.wait_for(
                self._sync_queue_impl(session, user_id, target_size),
                timeout=QUEUE_SYNC_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            logger.warning("queue_sync_timeout", user_id=str(user_id))
            await session.flush()
            return await self.get_queue(session, user_id)

    async def _sync_queue_impl(
        self,
        session: AsyncSession,
        user_id: UUID,
        target_size: int = TARGET_QUEUE_SIZE,
    ) -> list[QueueItemModel]:

        queue = await self._purge_heard_from_queue(session, user_id)

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

        queue = await self._append_from_songs_library(
            session,
            user_id,
            queue,
            target_size,
            pref=pref,
            filters=None,
            recent=recent,
        )

        if self._youtube_discovery_enabled(pref):
            queries = self._build_discovery_queries(pref, current=current)

            query_idx = 0
            attempts = 0
            seed_count = len(self._active_seeds(pref))
            max_attempts = min(target_size * 2 + seed_count * 2, 24)

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
                blocked_songs = await self.memory.get_blocked_song_ids(session, user_id)
                added_any = False
                for candidate in candidates:
                    if len(queue) >= target_size:
                        break
                    if self._skip_recommendation_candidate(
                        candidate, existing, existing_songs, blocked_songs
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

            if len(queue) < target_size:
                queue = await self._append_home_discovery(session, user_id, queue, target_size)

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
        seed_queries: list[str] | None = None,
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

        seeds = self._normalize_seeds(seed_queries)
        if not seeds and seed_query and seed_query.strip():
            seeds = self._normalize_seeds([seed_query])

        if from_preferences:
            await self._persist_active_seeds(session, pref, [])
        elif seeds:
            await self._persist_active_seeds(session, pref, seeds)

        queue = await self.get_queue(session, user_id)
        queue = await self._append_from_songs_library(
            session,
            user_id,
            queue,
            target_size,
            pref=pref,
            seeds=seeds or None,
            filters=filters,
            recent=recent,
        )

        queries = self._build_discovery_queries(
            pref,
            current=current,
            seed_queries=seeds or None,
            seed_query=seed_query,
            from_preferences=from_preferences,
            filters=filters,
        )

        if self._youtube_discovery_enabled(pref):
            query_idx = 0
            attempts = 0
            max_attempts = min(target_size * 2 + len(seeds) * 2, 24)
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
                blocked_songs = await self.memory.get_blocked_song_ids(session, user_id)
                added_any = False
                for candidate in candidates:
                    if len(queue) >= target_size:
                        break
                    if self._skip_recommendation_candidate(
                        candidate, existing, existing_songs, blocked_songs
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

            if len(queue) < target_size:
                queue = await self._append_home_discovery(session, user_id, queue, target_size)

        if queue and not any(q.is_current for q in queue):
            queue[0].is_current = True

        await session.flush()
        queue = await self._dedupe_queue(session, queue)
        active = self._active_seeds(pref)
        source = (
            "preferences"
            if from_preferences
            else ("search" if seeds or active else "current")
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
        queue = await self._append_from_songs_library(
            session,
            user_id,
            queue,
            target_size,
            pref=pref,
            recent=recent,
        )
        if self._youtube_discovery_enabled(pref):
            queries = self._build_discovery_queries(pref)
            query_idx = 0
            attempts = 0
            seed_count = len(self._active_seeds(pref))
            max_attempts = min(target_size * 2 + seed_count * 2, 24)

            while len(queue) < target_size and attempts < max_attempts:
                attempts += 1
                query = queries[query_idx % len(queries)]
                query_idx += 1
                candidates = await self._recommend(
                    session, user_id, query, limit=15, recent=recent
                )
                existing = await self._queue_track_ids(queue)
                existing_songs = await self._queue_song_ids(queue)
                blocked_songs = await self.memory.get_blocked_song_ids(session, user_id)
                added_any = False
                for candidate in candidates:
                    if len(queue) >= target_size:
                        break
                    if self._skip_recommendation_candidate(
                        candidate, existing, existing_songs, blocked_songs
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

            if len(queue) < target_size:
                queue = await self._append_home_discovery(session, user_id, queue, target_size)

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

        current = next((q for q in queue if q.is_current), None)
        if current and current.id != target.id:
            await session.delete(current)
            await session.flush()
            queue = await self.get_queue(session, user_id)
            target = next((q for q in queue if q.id == item_id), None)
            if not target:
                return None

        reordered = [target] + [q for q in queue if q.id != target.id]
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

    async def remove_queue_item(
        self, session: AsyncSession, user_id: UUID, item_id: UUID
    ) -> RemoveQueueResult | None:
        queue = await self.get_queue(session, user_id)
        target = next((q for q in queue if q.id == item_id), None)
        if not target:
            return None

        was_current = target.is_current
        next_provider_id = None
        if was_current and len(queue) > 1:
            current_idx = next((i for i, q in enumerate(queue) if q.id == item_id), 0)
            if current_idx + 1 < len(queue):
                next_provider_id = queue[current_idx + 1].provider_track_id

        await session.delete(target)
        await session.flush()

        queue = await self.get_queue(session, user_id)
        next_item: QueueItemModel | None = None

        if was_current and queue:
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
            next_item = queue[new_current_idx]
        elif queue:
            for i, q in enumerate(queue):
                q.position = i
            await session.flush()

        if not await self._is_playlist_mode(session, user_id):
            await self.sync_queue(session, user_id)
            queue = await self.get_queue(session, user_id)
            if was_current and next_item:
                for q in queue:
                    if q.provider_track_id == next_item.provider_track_id:
                        for x in queue:
                            x.is_current = False
                        q.is_current = True
                        next_item = q
                        break

        logger.info(
            "queue_item_removed",
            user_id=str(user_id),
            item_id=str(item_id),
            was_current=was_current,
        )
        return RemoveQueueResult(
            was_current=was_current,
            next_item=next_item,
            queue=queue,
        )

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
