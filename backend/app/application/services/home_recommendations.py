import random
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dto.schemas import TrackResponse
from app.application.services.language_utils import (
    build_random_home_queries,
    random_lang_discovery_query,
    resolve_languages_from_prefs,
)
from app.application.services.recommendation_engine import RecommendationEngine
from app.infrastructure.database.models import PlaylistItemModel, PlaylistModel, UserPreferencesModel


class HomeRecommendationService:
    def __init__(self, engine: RecommendationEngine):
        self.engine = engine

    async def get_home_sections(
        self, session: AsyncSession, user_id: UUID
    ) -> list[dict]:
        result = await session.execute(
            select(UserPreferencesModel).where(UserPreferencesModel.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()

        languages = resolve_languages_from_prefs(prefs)

        pl_result = await session.execute(
            select(PlaylistItemModel.song_id)
            .join(PlaylistModel, PlaylistItemModel.playlist_id == PlaylistModel.id)
            .where(PlaylistModel.user_id == user_id)
        )
        exclude_song_ids = set(pl_result.scalars().all())
        year_from = getattr(prefs, "discovery_year_from", None) if prefs else None
        year_to = getattr(prefs, "discovery_year_to", None) if prefs else None

        sections: list[dict] = []
        seen_ids: set[str] = set()

        home_queries = build_random_home_queries(languages, section_count=4)
        random.shuffle(home_queries)

        async def add_section(title: str, query: str, limit: int = 6) -> None:
            scored = await self.engine.recommend(
                session,
                user_id,
                query,
                limit=limit + len(seen_ids),
                exclude_song_ids=exclude_song_ids,
                year_from=year_from,
                year_to=year_to,
                preferred_languages=languages,
            )
            random.shuffle(scored)
            tracks: list[TrackResponse] = []
            for c in scored:
                tid = c.track.provider_track_id
                if tid in seen_ids:
                    continue
                seen_ids.add(tid)
                tracks.append(
                    TrackResponse(
                        provider=c.track.provider,
                        provider_track_id=c.track.provider_track_id,
                        title=c.track.title,
                        artist=c.track.artist,
                        album=c.track.album,
                        duration_seconds=c.track.duration_seconds,
                        thumbnail_url=c.track.thumbnail_url,
                        canonical_song_id=c.track.canonical_song_id,
                        score=c.score,
                    )
                )
                if len(tracks) >= limit:
                    break
            if tracks:
                sections.append({"title": title, "tracks": tracks})

        for hq in home_queries:
            await add_section(hq.title, hq.query)

        if not sections:
            lang = random.choice(languages)
            await add_section("Discover New Music", random_lang_discovery_query(lang))

        return sections
