"""Resolve YouTube video IDs for library songs (yt-dlp search, optional)."""

from __future__ import annotations

import asyncio
import logging
import re

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Song
from app.schemas import ResolveYoutubeResult, SongOut

logger = logging.getLogger(__name__)

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def build_search_query(song: Song) -> str:
    parts = [song.song_name]
    if song.movie_name:
        parts.append(song.movie_name)
    if song.composer_name:
        parts.append(song.composer_name)
    parts.append("official audio")
    return " ".join(p for p in parts if p)


def _search_youtube_sync(query: str) -> str | None:
    try:
        import yt_dlp
    except ImportError:
        logger.warning("yt_dlp_not_installed")
        return None

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)
            entries = (info or {}).get("entries") or []
            for entry in entries:
                if not entry:
                    continue
                vid = entry.get("id") or ""
                if VIDEO_ID_RE.match(vid):
                    return vid
    except Exception as exc:  # noqa: BLE001
        logger.warning("youtube_search_failed", extra={"error": str(exc), "query": query})
    return None


async def resolve_one_song(db: Session, song: Song) -> Song | None:
    """Resolve and persist YouTube video id for a single catalog song."""
    if song.youtube_video_id:
        return song
    q = build_search_query(song)
    video_id = await asyncio.to_thread(_search_youtube_sync, q)
    if not video_id:
        return None
    song.youtube_video_id = video_id
    song.playability = "mapped"
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
        video_id = await asyncio.to_thread(_search_youtube_sync, q)
        if not video_id:
            failed += 1
            continue
        if not dry_run:
            song.youtube_video_id = video_id
            song.playability = "mapped"
            updated.append(song)
            resolved += 1
        else:
            song.youtube_video_id = video_id  # ephemeral for response only
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
