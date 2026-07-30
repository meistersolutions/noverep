"""Resolve YouTube video IDs and popularity from view counts.

Prefer the official YouTube Data API when ``YOUTUBE_API_KEY`` is set (works from
Render datacenter IPs). Fall back to yt-dlp search, which often gets HTTP 403
from cloud hosts without cookies.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import math
import re
import tempfile
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Song
from app.schemas import ResolveYoutubeResult, SongOut

logger = logging.getLogger(__name__)

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# log10(1_000_000_000) — ~1B views maps to popularity 100.
_VIEW_SCORE_LOG_MAX = 9.0

# Soft circuit-breaker after YouTube blocks (403 / bot checks).
_consecutive_blocks = 0


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


def youtube_block_cooldown_seconds() -> float:
    """Extra sleep after consecutive YouTube blocks."""
    if _consecutive_blocks <= 0:
        return 0.0
    base = float(settings.youtube_resolve_403_cooldown_seconds)
    return min(600.0, base * min(_consecutive_blocks, 5))


def _note_block(reason: str, *, query: str | None = None) -> None:
    global _consecutive_blocks
    _consecutive_blocks += 1
    logger.warning(
        "youtube_blocked",
        extra={
            "reason": reason,
            "query": query,
            "consecutive_blocks": _consecutive_blocks,
        },
    )


def _note_ok() -> None:
    global _consecutive_blocks
    _consecutive_blocks = 0


def _youtube_cookiefile() -> str | None:
    """Resolve a Netscape cookies.txt path for yt-dlp (Render-friendly)."""
    file_path = (settings.youtube_cookies_file or "").strip()
    if file_path and Path(file_path).is_file():
        return file_path

    raw = (settings.youtube_cookies or "").strip()
    if not raw and settings.youtube_cookies_b64:
        try:
            raw = base64.b64decode(settings.youtube_cookies_b64).decode("utf-8")
        except Exception:  # noqa: BLE001
            logger.warning("youtube_cookies_b64_invalid")
            return None
    if not raw:
        return None
    try:
        path = Path(tempfile.gettempdir()) / "songs_library_youtube_cookies.txt"
        path.write_text(raw, encoding="utf-8")
        return str(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("youtube_cookies_write_failed", extra={"error": str(exc)})
        return None


def _is_block_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(
        token in text
        for token in (
            "403",
            "forbidden",
            "sign in to confirm",
            "not a bot",
            "too many requests",
            "429",
        )
    )


def _ydl_opts(*, extract_flat: bool = False) -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 25,
        "retries": 2,
        "extractor_retries": 2,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
        "extractor_args": {
            "youtube": {
                # Avoid clients YouTube currently rejects hard from datacenters.
                "player_client": ["android", "ios", "mweb", "tv", "web"],
            }
        },
    }
    if extract_flat:
        opts["extract_flat"] = "in_playlist"
    else:
        opts["noplaylist"] = True
    cookiefile = _youtube_cookiefile()
    if cookiefile:
        opts["cookiefile"] = cookiefile
    return opts


def _search_via_data_api(query: str) -> tuple[str | None, int | None]:
    key = (settings.youtube_api_key or "").strip()
    if not key:
        return None, None
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part": "snippet",
                    "type": "video",
                    "maxResults": 5,
                    "q": query,
                    "key": key,
                },
            )
            if resp.status_code in {403, 429}:
                _note_block(f"data_api_search_{resp.status_code}", query=query)
                return None, None
            resp.raise_for_status()
            items = (resp.json() or {}).get("items") or []
            for item in items:
                vid = ((item.get("id") or {}).get("videoId") or "").strip()
                if not VIDEO_ID_RE.match(vid):
                    continue
                views = _views_via_data_api(client, vid)
                _note_ok()
                return vid, views
    except Exception as exc:  # noqa: BLE001
        if _is_block_error(exc):
            _note_block(str(exc), query=query)
        else:
            logger.warning(
                "youtube_data_api_search_failed",
                extra={"error": str(exc), "query": query},
            )
    return None, None


def _views_via_data_api(client: httpx.Client, video_id: str) -> int | None:
    key = (settings.youtube_api_key or "").strip()
    if not key:
        return None
    try:
        resp = client.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={
                "part": "statistics",
                "id": video_id,
                "key": key,
            },
        )
        if resp.status_code in {403, 429}:
            return None
        resp.raise_for_status()
        items = (resp.json() or {}).get("items") or []
        if not items:
            return None
        raw = ((items[0].get("statistics") or {}).get("viewCount")) or None
        if raw is None:
            return None
        views = int(raw)
        return views if views > 0 else None
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "youtube_data_api_views_failed",
            extra={"error": str(exc), "video_id": video_id},
        )
        return None


def _fetch_view_count_data_api(video_id: str) -> int | None:
    key = (settings.youtube_api_key or "").strip()
    if not key:
        return None
    try:
        with httpx.Client(timeout=20.0) as client:
            return _views_via_data_api(client, video_id)
    except Exception:  # noqa: BLE001
        return None


def _search_youtube_sync(query: str) -> tuple[str | None, int | None]:
    """Return (video_id, view_count) for the first search hit."""
    api_hit = _search_via_data_api(query)
    if api_hit[0]:
        return api_hit

    try:
        import yt_dlp
    except ImportError:
        logger.warning("yt_dlp_not_installed")
        return None, None

    try:
        with yt_dlp.YoutubeDL(_ydl_opts(extract_flat=True)) as ydl:
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
                    # Flat search often omits views — fetch the watch page / API.
                    views = _fetch_view_count_sync(vid)
                _note_ok()
                return vid, views if isinstance(views, int) and views > 0 else None
    except Exception as exc:  # noqa: BLE001
        if _is_block_error(exc):
            _note_block(str(exc), query=query)
        logger.warning("youtube_search_failed", extra={"error": str(exc), "query": query})
    return None, None


def _fetch_view_count_sync(video_id: str) -> int | None:
    """Load view_count for a known video id."""
    views = _fetch_view_count_data_api(video_id)
    if views is not None:
        return views

    try:
        import yt_dlp
    except ImportError:
        return None
    try:
        with yt_dlp.YoutubeDL(_ydl_opts(extract_flat=False)) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}",
                download=False,
            )
            views = (info or {}).get("view_count")
            if isinstance(views, int) and views > 0:
                return views
    except Exception as exc:  # noqa: BLE001
        if _is_block_error(exc):
            _note_block(str(exc), query=video_id)
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
            # Back off within the batch when YouTube is blocking hard.
            cooldown = youtube_block_cooldown_seconds()
            if cooldown >= settings.youtube_resolve_403_cooldown_seconds:
                await asyncio.sleep(min(cooldown, 30.0))
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
        await asyncio.sleep(0.35)

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
        await asyncio.sleep(0.2)

    if updated:
        db.commit()
    return {"attempted": len(songs), "updated": updated, "failed": failed}
