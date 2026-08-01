from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import MEMORY_WINDOW_DAYS, MemoryWindow
from app.infrastructure.database.models import (
    AlbumModel,
    ListeningHistoryModel,
    SongModel,
    UserPreferencesModel,
)


@dataclass(frozen=True)
class HeardSongSnapshot:
    song_id: UUID
    title: str
    artist: str
    duration_seconds: int | None
    album: str | None = None


class MemoryService:
    """Enforces never-repeat policy within configurable memory windows."""

    async def get_memory_window(self, session: AsyncSession, user_id: UUID) -> MemoryWindow:
        result = await session.execute(
            select(UserPreferencesModel).where(UserPreferencesModel.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()
        if not prefs or prefs.repeat_disabled:
            return MemoryWindow.ONE_DAY  # minimal window when disabled
        try:
            return MemoryWindow(prefs.memory_window)
        except ValueError:
            return MemoryWindow.THIRTY_DAYS

    async def is_repeat_allowed(
        self,
        session: AsyncSession,
        user_id: UUID,
        song_id: UUID,
        explicitly_requested: bool = False,
    ) -> bool:
        if explicitly_requested:
            return True

        result = await session.execute(
            select(UserPreferencesModel).where(UserPreferencesModel.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()
        if prefs and prefs.repeat_disabled:
            return True

        window = await self.get_memory_window(session, user_id)
        days = MEMORY_WINDOW_DAYS[window]
        if days is None:  # forever
            cutoff = datetime(1970, 1, 1, tzinfo=UTC)
        else:
            cutoff = datetime.now(UTC) - timedelta(days=days)

        history = await session.execute(
            select(ListeningHistoryModel).where(
                and_(
                    ListeningHistoryModel.user_id == user_id,
                    ListeningHistoryModel.song_id == song_id,
                    ListeningHistoryModel.played_at >= cutoff,
                    ListeningHistoryModel.explicitly_requested.is_(False),
                )
            )
        )
        return history.scalar_one_or_none() is None

    async def get_blocked_song_ids(
        self, session: AsyncSession, user_id: UUID
    ) -> set[UUID]:
        window = await self.get_memory_window(session, user_id)
        days = MEMORY_WINDOW_DAYS[window]

        result = await session.execute(
            select(UserPreferencesModel).where(UserPreferencesModel.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()
        if prefs and prefs.repeat_disabled:
            return set()

        query = select(ListeningHistoryModel.song_id).where(
            ListeningHistoryModel.user_id == user_id,
            ListeningHistoryModel.explicitly_requested.is_(False),
        )
        if days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=days)
            query = query.where(ListeningHistoryModel.played_at >= cutoff)

        rows = await session.execute(query.distinct())
        return {row[0] for row in rows.all()}

    async def _history_cutoff(
        self, session: AsyncSession, user_id: UUID
    ) -> datetime | None:
        """Return played_at cutoff, or None when repeat is disabled (no filtering)."""
        result = await session.execute(
            select(UserPreferencesModel).where(UserPreferencesModel.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()
        if prefs and prefs.repeat_disabled:
            return None

        window = await self.get_memory_window(session, user_id)
        days = MEMORY_WINDOW_DAYS[window]
        if days is None:
            return datetime(1970, 1, 1, tzinfo=UTC)
        return datetime.now(UTC) - timedelta(days=days)

    async def get_heard_song_snapshots(
        self, session: AsyncSession, user_id: UUID
    ) -> list[HeardSongSnapshot]:
        """Heard songs within the user's memory window (cross-device history)."""
        cutoff = await self._history_cutoff(session, user_id)
        if cutoff is None:
            return []

        query = (
            select(
                ListeningHistoryModel.song_id,
                SongModel.title,
                ListeningHistoryModel.artist_name,
                SongModel.duration_seconds,
                func.coalesce(ListeningHistoryModel.album_name, AlbumModel.title),
            )
            .join(SongModel, ListeningHistoryModel.song_id == SongModel.id)
            .outerjoin(AlbumModel, SongModel.album_id == AlbumModel.id)
            .where(
                ListeningHistoryModel.user_id == user_id,
                ListeningHistoryModel.explicitly_requested.is_(False),
                ListeningHistoryModel.played_at >= cutoff,
            )
            .distinct()
        )
        rows = await session.execute(query)
        return [
            HeardSongSnapshot(
                song_id=row[0],
                title=row[1],
                artist=row[2],
                duration_seconds=row[3],
                album=row[4],
            )
            for row in rows.all()
        ]

    async def record_play(
        self,
        session: AsyncSession,
        user_id: UUID,
        song_id: UUID,
        provider: str,
        artist: str,
        album: str | None,
        genre: str | None,
        session_id: UUID,
        duration_listened: int,
        completion_pct: float,
        skipped: bool,
        device_id: str | None,
        explicitly_requested: bool = False,
    ) -> ListeningHistoryModel:
        cutoff = datetime.now(UTC) - timedelta(hours=4)
        existing_result = await session.execute(
            select(ListeningHistoryModel)
            .where(
                ListeningHistoryModel.user_id == user_id,
                ListeningHistoryModel.song_id == song_id,
                ListeningHistoryModel.session_id == session_id,
                ListeningHistoryModel.played_at >= cutoff,
            )
            .order_by(ListeningHistoryModel.played_at.desc())
            .limit(1)
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            existing.duration_listened = max(existing.duration_listened, duration_listened)
            existing.completion_pct = max(existing.completion_pct, completion_pct)
            existing.skipped = existing.skipped or skipped
            # Real listen/skip must count toward no-repeat even if the start
            # event was marked explicitly_requested (e.g. buggy native clients).
            if duration_listened > 0 or skipped:
                existing.explicitly_requested = False
            elif explicitly_requested:
                existing.explicitly_requested = True
            if album:
                existing.album_name = album
            if genre:
                existing.genre_name = genre
            await session.flush()
            return existing

        entry = ListeningHistoryModel(
            user_id=user_id,
            song_id=song_id,
            provider=provider,
            artist_name=artist,
            album_name=album,
            genre_name=genre,
            session_id=session_id,
            duration_listened=duration_listened,
            completion_pct=completion_pct,
            skipped=skipped,
            device_id=device_id,
            explicitly_requested=explicitly_requested,
        )
        session.add(entry)
        await session.flush()
        return entry

    async def get_repeat_avoidance_count(self, session: AsyncSession, user_id: UUID) -> int:
        result = await session.execute(
            select(func.count(ListeningHistoryModel.id)).where(
                ListeningHistoryModel.user_id == user_id,
                ListeningHistoryModel.skipped.is_(False),
            )
        )
        return result.scalar() or 0
