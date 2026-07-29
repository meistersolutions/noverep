"""Resolve YouTube video IDs and popularity from view counts (yt-dlp)."""

from __future__ import annotations

import asyncio
import logging
import math
import re

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Song
from app.schemas import ResolveYoutubeResult, SongOut

logger = logging.getLogger(__name__)

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# log10(1_000_000_000) — ~1B views maps to popularity 100.
_VIEW_SCORE_LOG_MAX = 9.0


def popularity_from_view_count(views: int | float | None) -> float | None:
    """Map YouTube view count to a 0–100 popularity score (log scale).

    Examples (approx):
      1,000 views → 33
      100,000 → 56
      1,000,000 → 67
      10,000,000 → 78
      100,000,000 → 89
      1,000,000,000 → 100
    """
    if views is None:
        return None
    try:
        n = int(views)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    score = 100.0 * math.log10(n) / _VIEW_SCORE_LOG_MAX
    return round(min(100.0, max(1.0, score)), 2)


def build_search_query(song: Song) -> str:
    parts = [song.song_name]
    if song.movie_name:
        parts.append(song.movie_name)
    if song.composer_name:
        parts.append(song.composer_name)
    parts.append("official audio")
    return " ".join(p for p in parts if p)


def _search_youtube_sync(query: str) -> tuple[str | None, int | None]:
    """Return (video_id, view_count) for the first search hit."""
    try:
        import yt_dlp
    except ImportError:
        logger.warning("yt_dlp_not_installed")
        return None, None

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)
            entries = (info or {}).get("entries") or []
            for entry in entries:
                if not entry:
                    continue
                vid = entry.get("id") or ""
                if not VIDEO_ID_RE.match(vid):
                    continue
                views = entry.get("view_count")
                if not isinstance(views, int) or views <= 0:
                    # Flat search often omits views — fetch the watch page.
                    views = _fetch_view_count_sync(vid)
                return vid, views if isinstance(views, int) and views > 0 else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("youtube_search_failed", extra={"error": str(exc), "query": query})
    return None, None


def _fetch_view_count_sync(video_id: str) -> int | None:
    """Load view_count for a known video id."""
    try:
        import yt_dlp
    except ImportError:
        return None
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}",
                download=False,
            )
            views = (info or {}).get("view_count")
            if isinstance(views, int) and views > 0:
                return views
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "youtube_view_count_failed",
            extra={"error": str(exc), "video_id": video_id},
        )
    return None


def apply_youtube_stats(song: Song, *, video_id: str, views: int | None) -> None:
    song.youtube_video_id = video_id
    song.playability = "mapped"
    if views is not None and views > 0:
        song.youtube_view_count = views
        score = popularity_from_view_count(views)
        if score is not None:
            song.popularity = score


async def resolve_one_song(db: Session, song: Song) -> Song | None:
    """Resolve YouTube id (if needed) and set popularity from view count."""
    video_id = song.youtube_video_id
    views: int | None = None

    if video_id and VIDEO_ID_RE.match(video_id):
        views = await asyncio.to_thread(_fetch_view_count_sync, video_id)
        if views is None and song.youtube_view_count:
            # Keep existing mapping even if stats fetch failed.
            return song
        if views is not None:
            apply_youtube_stats(song, video_id=video_id, views=views)
            db.commit()
            db.refresh(song)
        return song

    q = build_search_query(song)
    video_id, views = await asyncio.to_thread(_search_youtube_sync, q)
    if not video_id:
        return None
    apply_youtube_stats(song, video_id=video_id, views=views)
    db.commit()
    db.refresh(song)
    return song


async def resolve_unmapped(
    db: Session,
    *,
    limit: int | None = None,
    composer: str | None = None,
    dry_run: bool = False,
) -> ResolveYoutubeResult:
    limit = limit or settings.youtube_resolve_limit
    query = db.query(Song).filter(Song.youtube_video_id.is_(None))
    if composer:
        query = query.filter(Song.composer_name.ilike(f"%{composer}%"))
    songs = query.order_by(Song.popularity.desc()).limit(limit).all()

    resolved = 0
    failed = 0
    updated: list[Song] = []

    for song in songs:
        q = build_search_query(song)
        video_id, views = await asyncio.to_thread(_search_youtube_sync, q)
        if not video_id:
            failed += 1
            continue
        if not dry_run:
            apply_youtube_stats(song, video_id=video_id, views=views)
            updated.append(song)
            resolved += 1
        else:
            song.youtube_video_id = video_id
            if views is not None:
                song.youtube_view_count = views
                score = popularity_from_view_count(views)
                if score is not None:
                    song.popularity = score
            updated.append(song)
            resolved += 1

    if not dry_run and updated:
        db.commit()
        for song in updated:
            db.refresh(song)

    return ResolveYoutubeResult(
        attempted=len(songs),
        resolved=resolved,
        failed=failed,
        songs=[SongOut.model_validate(s) for s in updated],
    )


async def refresh_popularity_from_views(
    db: Session,
    *,
    limit: int | None = None,
    force: bool = False,
) -> dict[str, int]:
    """Update popularity for mapped songs using live YouTube view counts.

    By default only songs missing ``youtube_view_count`` are refreshed.
    """
    limit = limit or settings.youtube_resolve_batch_size
    query = db.query(Song).filter(Song.youtube_video_id.isnot(None))
    if not force:
        query = query.filter(Song.youtube_view_count.is_(None))
    songs = query.order_by(Song.updated_at.asc()).limit(limit).all()

    updated = 0
    failed = 0
    for song in songs:
        vid = song.youtube_video_id or ""
        if not VIDEO_ID_RE.match(vid):
            failed += 1
            continue
        views = await asyncio.to_thread(_fetch_view_count_sync, vid)
        if views is None:
            failed += 1
            continue
        apply_youtube_stats(song, video_id=vid, views=views)
        updated += 1

    if updated:
        db.commit()
    return {"attempted": len(songs), "updated": updated, "failed": failed}
