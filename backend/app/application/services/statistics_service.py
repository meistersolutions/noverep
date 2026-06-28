from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import ListeningHistoryModel


class StatisticsService:
    async def get_dashboard(self, session: AsyncSession, user_id: UUID) -> dict:
        history = await session.execute(
            select(ListeningHistoryModel).where(ListeningHistoryModel.user_id == user_id)
        )
        entries = list(history.scalars().all())

        artists = {e.artist_name for e in entries}
        genres = {e.genre_name for e in entries if e.genre_name}
        albums = {e.album_name for e in entries if e.album_name}

        genre_counts: dict[str, int] = {}
        artist_counts: dict[str, int] = {}
        hour_counts = [0] * 24
        day_counts: dict[str, int] = {}

        for e in entries:
            if e.genre_name:
                genre_counts[e.genre_name] = genre_counts.get(e.genre_name, 0) + 1
            artist_counts[e.artist_name] = artist_counts.get(e.artist_name, 0) + 1
            if e.played_at:
                hour_counts[e.played_at.hour] += 1
                day_key = e.played_at.strftime("%Y-%m-%d")
                day_counts[day_key] = day_counts.get(day_key, 0) + 1

        top_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        top_artists = sorted(artist_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        streak = self._compute_streak(day_counts)
        discovery_score = min(100, len(artists) * 2 + len(genres) * 3)

        return {
            "songs_played": len(entries),
            "artists_explored": len(artists),
            "genres_explored": len(genres),
            "albums_explored": len(albums),
            "listening_streak_days": streak,
            "repeat_avoidance_count": len(entries),
            "discovery_score": discovery_score,
            "most_explored_genres": [{"name": g, "count": c} for g, c in top_genres],
            "top_artists": [{"name": a, "count": c} for a, c in top_artists],
            "listening_by_hour": hour_counts,
            "listening_heatmap": day_counts,
        }

    def _compute_streak(self, day_counts: dict[str, int]) -> int:
        if not day_counts:
            return 0
        streak = 0
        day = datetime.now(UTC).date()
        while True:
            key = day.isoformat()
            if key in day_counts:
                streak += 1
                day -= timedelta(days=1)
            else:
                break
        return streak
