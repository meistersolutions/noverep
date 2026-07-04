import asyncio
import random
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.memory_service import MemoryService
from app.application.services.song_matcher import is_same_song
from app.application.services.song_normalizer import SongNormalizer
from app.infrastructure.database.models import SongModel
from app.domain.entities import ProviderTrack, RecommendationWeights, ScoredCandidate
from app.domain.interfaces import MusicProvider

logger = structlog.get_logger()

QUICK_SEARCH_TIMEOUT_SEC = 50.0


def _effective_release_year(song: SongModel, track: ProviderTrack) -> int | None:
    meta = song.enrichment_metadata or {}
    mb_year = meta.get("release_year")
    if isinstance(mb_year, int):
        return mb_year
    if song.release_year:
        return song.release_year
    return track.release_year


def _safe_lower(value: str | None) -> str:
    return (value or "").strip().lower()


class RecommendationEngine:
    """
    Modular pipeline: search → normalize → dedupe → filter → score → sort → randomize.
    """

    def __init__(
        self,
        providers: dict[str, MusicProvider],
        memory_service: MemoryService,
        normalizer: SongNormalizer,
    ):
        self.providers = providers
        self.memory = memory_service
        self.normalizer = normalizer

    async def get_weights(self, session: AsyncSession, user_id: UUID) -> RecommendationWeights:
        from app.infrastructure.database.models import UserPreferencesModel
        from sqlalchemy import select

        result = await session.execute(
            select(UserPreferencesModel).where(UserPreferencesModel.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()
        if prefs and prefs.recommendation_weights:
            w = prefs.recommendation_weights
            return RecommendationWeights(
                artist_diversity=w.get("artist_diversity", 1.0),
                genre_diversity=w.get("genre_diversity", 1.0),
                album_diversity=w.get("album_diversity", 0.8),
                language_diversity=w.get("language_diversity", 0.6),
                year_diversity=w.get("year_diversity", 0.5),
                popularity=w.get("popularity", 0.7),
                freshness=w.get("freshness", 0.9),
                randomness=w.get("randomness", 0.4),
                time_of_day=w.get("time_of_day", 0.3),
                history_penalty=w.get("history_penalty", 1.2),
                session_length=w.get("session_length", 0.2),
            )
        return RecommendationWeights()

    async def recommend(
        self,
        session: AsyncSession,
        user_id: UUID,
        query: str,
        provider_name: str = "youtube",
        limit: int = 20,
        recent_artists: list[str] | None = None,
        recent_genres: list[str] | None = None,
        recent_albums: list[str] | None = None,
        recent_languages: list[str] | None = None,
        recent_decades: list[int] | None = None,
        skip_memory_filter: bool = False,
        exclude_song_ids: set[UUID] | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        preferred_languages: list[str] | None = None,
    ) -> list[ScoredCandidate]:
        from app.application.services.language_utils import (
            augment_search_query,
            filter_tracks_by_language,
            resolve_languages_from_prefs,
        )
        from app.infrastructure.database.models import UserPreferencesModel
        from sqlalchemy import select

        recent_artists = recent_artists or []
        recent_genres = recent_genres or []
        recent_albums = recent_albums or []
        recent_languages = recent_languages or []
        recent_decades = recent_decades or []

        provider = self.providers.get(provider_name)
        if not provider:
            return []

        if preferred_languages is None:
            pref_result = await session.execute(
                select(UserPreferencesModel).where(UserPreferencesModel.user_id == user_id)
            )
            pref = pref_result.scalar_one_or_none()
            preferred_languages = resolve_languages_from_prefs(pref)

        search_query = augment_search_query(query, preferred_languages)

        # 1. Search
        candidates = await provider.search(search_query, limit=limit * 3)

        # 2. Normalize & resolve canonical IDs
        for track in candidates:
            song = await self.normalizer.resolve_canonical(track, session)
            track.canonical_song_id = song.id
            resolved_year = _effective_release_year(song, track)
            if resolved_year:
                track.release_year = resolved_year

        # 3. Remove duplicates (same canonical song or semantically same track)
        seen: set[UUID] = set()
        unique: list[ProviderTrack] = []
        for track in candidates:
            if track.canonical_song_id and track.canonical_song_id in seen:
                continue
            if any(
                is_same_song(
                    track.title,
                    track.artist,
                    track.duration_seconds,
                    kept.title,
                    kept.artist,
                    kept.duration_seconds,
                )
                for kept in unique
            ):
                continue
            if track.canonical_song_id:
                seen.add(track.canonical_song_id)
            unique.append(track)

        # 4. Memory filter – remove blocked songs (unless include heard / allow replays)
        if skip_memory_filter:
            filtered = unique
        else:
            blocked = await self.memory.get_blocked_song_ids(session, user_id)
            filtered = [t for t in unique if t.canonical_song_id not in blocked]

        # 5. Block lists from preferences
        filtered = await self._apply_user_blocks(session, user_id, filtered)

        # 5a. Language preference filter
        filtered = filter_tracks_by_language(filtered, preferred_languages)

        # 5b. Exclude playlist songs from discovery
        if exclude_song_ids:
            filtered = [
                t
                for t in filtered
                if not t.canonical_song_id or t.canonical_song_id not in exclude_song_ids
            ]

        # 5c. Year range filter (MusicBrainz / canonical year when available)
        if year_from or year_to:
            y_min = year_from or 1900
            y_max = year_to or 2100
            filtered = [
                t
                for t in filtered
                if t.release_year is not None and y_min <= t.release_year <= y_max
            ]

        # 6. Score
        weights = await self.get_weights(session, user_id)
        scored = [
            self._score_track(
                track,
                weights,
                recent_artists,
                recent_genres,
                recent_albums,
                recent_languages,
                recent_decades,
            )
            for track in filtered
        ]

        # 7. Sort
        scored.sort(key=lambda c: c.score, reverse=True)

        # 8. Randomize – heavy shuffle for surprise discovery
        if len(scored) > 1:
            random.shuffle(scored)

        return scored[:limit]

    async def raw_search(
        self,
        query: str,
        provider_name: str = "youtube",
        limit: int = 20,
    ) -> list[ScoredCandidate]:
        """Literal search — user query only, song-filter at provider (no prefs/blocks)."""
        provider = self.providers.get(provider_name)
        if not provider:
            return []

        search_query = query.strip()
        if not search_query:
            return []

        try:
            candidates = await asyncio.wait_for(
                provider.search(search_query, limit=limit + 10, raw=True),
                timeout=QUICK_SEARCH_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            logger.warning("raw_search_timeout", query=query)
            candidates = []
        except Exception as e:
            logger.exception("raw_search_provider_failed", query=query, error=str(e))
            candidates = []

        seen: set[str] = set()
        unique: list[ProviderTrack] = []
        for track in candidates:
            if track.provider_track_id in seen:
                continue
            seen.add(track.provider_track_id)
            unique.append(track)

        return [
            ScoredCandidate(track=t, score=t.popularity, reasons={"raw": 1.0})
            for t in unique[:limit]
        ]

    async def quick_search(
        self,
        session: AsyncSession,
        user_id: UUID,
        query: str,
        provider_name: str = "youtube",
        limit: int = 20,
        skip_memory_filter: bool = False,
        preferred_languages: list[str] | None = None,
    ) -> list[ScoredCandidate]:
        """Fast search — YouTube lookup only, no per-track DB canonical resolution."""
        from app.application.services.language_utils import (
            augment_search_query,
            filter_tracks_by_language,
            resolve_languages_from_prefs,
        )
        from app.infrastructure.database.models import UserPreferencesModel
        from sqlalchemy import select

        provider = self.providers.get(provider_name)
        if not provider:
            return []

        if preferred_languages is None:
            pref_result = await session.execute(
                select(UserPreferencesModel).where(UserPreferencesModel.user_id == user_id)
            )
            pref = pref_result.scalar_one_or_none()
            preferred_languages = resolve_languages_from_prefs(pref)

        search_query = augment_search_query(query, preferred_languages)
        try:
            candidates = await asyncio.wait_for(
                provider.search(search_query, limit=limit + 10),
                timeout=QUICK_SEARCH_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            logger.warning("quick_search_timeout", query=query)
            candidates = []
        except Exception as e:
            logger.exception("quick_search_provider_failed", query=query, error=str(e))
            candidates = []

        seen: set[str] = set()
        unique: list[ProviderTrack] = []
        for track in candidates:
            if track.provider_track_id in seen:
                continue
            seen.add(track.provider_track_id)
            unique.append(track)

        filtered = await self._apply_user_blocks(session, user_id, unique)
        filtered = filter_tracks_by_language(filtered, preferred_languages)

        return [
            ScoredCandidate(track=t, score=t.popularity, reasons={"quick": 1.0})
            for t in filtered[:limit]
        ]

    async def _apply_user_blocks(
        self, session: AsyncSession, user_id: UUID, tracks: list[ProviderTrack]
    ) -> list[ProviderTrack]:
        from app.infrastructure.database.models import UserPreferencesModel
        from sqlalchemy import select

        result = await session.execute(
            select(UserPreferencesModel).where(UserPreferencesModel.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()
        if not prefs:
            return tracks

        blocked_artists = {_safe_lower(a) for a in (prefs.blocked_artists or []) if isinstance(a, str)}
        blocked_albums = {_safe_lower(a) for a in (prefs.blocked_albums or []) if isinstance(a, str)}
        blocked_songs = {_safe_lower(s) for s in (prefs.blocked_songs or []) if isinstance(s, str)}

        return [
            t
            for t in tracks
            if _safe_lower(t.artist) not in blocked_artists
            and (not t.album or _safe_lower(t.album) not in blocked_albums)
            and _safe_lower(t.title) not in blocked_songs
        ]

    def _score_track(
        self,
        track: ProviderTrack,
        weights: RecommendationWeights,
        recent_artists: list[str],
        recent_genres: list[str],
        recent_albums: list[str],
        recent_languages: list[str],
        recent_decades: list[int],
    ) -> ScoredCandidate:
        reasons: dict[str, float] = {}
        score = 0.0

        # Artist diversity
        if track.artist.lower() in [a.lower() for a in recent_artists[-3:]]:
            reasons["artist_penalty"] = -weights.artist_diversity * 2.0
        else:
            reasons["artist_bonus"] = weights.artist_diversity * 0.5

        # Genre diversity
        genre = track.genre or "unknown"
        if genre.lower() in [g.lower() for g in recent_genres[-3:]]:
            reasons["genre_penalty"] = -weights.genre_diversity * 1.5
        else:
            reasons["genre_bonus"] = weights.genre_diversity * 0.4

        # Album diversity
        if track.album and track.album.lower() in [a.lower() for a in recent_albums[-2:]]:
            reasons["album_penalty"] = -weights.album_diversity * 1.2

        # Language diversity
        lang = track.language or "unknown"
        if lang.lower() in [l.lower() for l in recent_languages[-3:]]:
            reasons["language_penalty"] = -weights.language_diversity

        # Decade diversity
        if track.release_year:
            decade = (track.release_year // 10) * 10
            if decade in recent_decades[-3:]:
                reasons["decade_penalty"] = -weights.year_diversity

        # Popularity & freshness
        reasons["popularity"] = track.popularity * weights.popularity * 0.1
        if track.release_year:
            age = datetime.now(UTC).year - track.release_year
            freshness = max(0, 1 - age / 50) * weights.freshness
            reasons["freshness"] = freshness

        # Time of day (placeholder heuristic)
        hour = datetime.now(UTC).hour
        if 6 <= hour < 12:
            reasons["time_of_day"] = weights.time_of_day * 0.2
        elif 18 <= hour < 24:
            reasons["time_of_day"] = weights.time_of_day * 0.3

        # Randomness
        reasons["randomness"] = random.random() * weights.randomness

        score = sum(reasons.values())
        return ScoredCandidate(track=track, score=score, reasons=reasons)
