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

# Last background / manual resolve batch (in-process; resets on redeploy).
_last_resolve: dict = {
    "at": None,
    "source": None,
    "attempted": 0,
    "resolved": 0,
    "failed": 0,
}


def get_resolve_status() -> dict:
    """Snapshot for the Songs Library portal /ops monitoring."""
    from app.services.youtube_playwright import playwright_status

    return {
        "youtube_api_configured": _data_api_configured(),
        "playwright": playwright_status(),
        "consecutive_blocks": _consecutive_blocks,
        "block_cooldown_seconds": youtube_block_cooldown_seconds(),
        "last_batch": dict(_last_resolve),
    }


def _record_resolve_batch(
    *,
    source: str,
    attempted: int,
    resolved: int,
    failed: int,
) -> None:
    from datetime import datetime, timezone

    _last_resolve.update(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "attempted": attempted,
            "resolved": resolved,
            "failed": failed,
        }
    )


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


def build_search_queries(song: Song) -> list[str]:
    """Ordered search attempts — broader queries after the full metadata string.

    Keep the list short when the Data API key is set: each search costs 100
    quota units (~100 searches/day on the free tier).
    """
    queries: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        q = " ".join(value.split()).strip()
        if not q:
            return
        key = q.casefold()
        if key in seen:
            return
        seen.add(key)
        queries.append(q)

    add(build_search_query(song))
    if song.movie_name:
        add(f"{song.song_name} {song.movie_name}")
    # Extra composer / title-only attempts only without Data API (yt-dlp path).
    if not _data_api_configured():
        if song.composer_name:
            add(f"{song.song_name} {song.composer_name}")
        add(song.song_name)
    elif len(queries) == 1:
        add(song.song_name)
    return queries


def _youtube_api_key() -> str:
    return (settings.youtube_api_key or "").strip()


def _data_api_configured() -> bool:
    return bool(_youtube_api_key())


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


def _data_api_region_params(language: str | None) -> dict[str, str]:
    """Bias Indian film-music search when we know the song language."""
    lang = (language or "").strip().casefold()
    if lang in {"tamil", "tamizh", "ta", "தமிழ்"}:
        return {"relevanceLanguage": "ta", "regionCode": "IN"}
    if lang in {"hindi", "hi", "हिंदी", "हिन्दी"}:
        return {"relevanceLanguage": "hi", "regionCode": "IN"}
    if lang in {"telugu", "te"}:
        return {"relevanceLanguage": "te", "regionCode": "IN"}
    if lang in {"malayalam", "ml"}:
        return {"relevanceLanguage": "ml", "regionCode": "IN"}
    if lang in {"kannada", "kn"}:
        return {"relevanceLanguage": "kn", "regionCode": "IN"}
    return {"regionCode": "IN"}


def _search_via_data_api(
    query: str,
    *,
    language: str | None = None,
) -> tuple[str | None, int | None]:
    key = _youtube_api_key()
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
                    **_data_api_region_params(language),
                },
            )
            if resp.status_code in {403, 429}:
                detail = _google_api_error(resp)
                _note_block(f"data_api_search_{resp.status_code}: {detail}", query=query)
                return None, None
            if resp.status_code != 200:
                logger.warning(
                    "youtube_data_api_search_failed",
                    extra={
                        "status": resp.status_code,
                        "error": _google_api_error(resp),
                        "query": query,
                    },
                )
                return None, None
            items = (resp.json() or {}).get("items") or []
            if not items:
                logger.info(
                    "youtube_data_api_search_empty",
                    extra={"query": query},
                )
                return None, None
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


def _google_api_error(resp: httpx.Response) -> str:
    try:
        payload = resp.json()
        err = (payload or {}).get("error") or {}
        message = err.get("message") or ""
        reason = ""
        errors = err.get("errors") or []
        if errors and isinstance(errors[0], dict):
            reason = str(errors[0].get("reason") or "")
        parts = [p for p in (message, reason) if p]
        if parts:
            return " — ".join(parts)
    except Exception:  # noqa: BLE001
        pass
    return (resp.text or "")[:240]


def _views_via_data_api(client: httpx.Client, video_id: str) -> int | None:
    key = _youtube_api_key()
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
    key = _youtube_api_key()
    if not key:
        return None
    try:
        with httpx.Client(timeout=20.0) as client:
            return _views_via_data_api(client, video_id)
    except Exception:  # noqa: BLE001
        return None


def _search_youtube_sync(
    query: str,
    *,
    language: str | None = None,
) -> tuple[str | None, int | None]:
    """Return (video_id, view_count) for the first search hit.

    Order: Data API → yt-dlp → Playwright (when enabled and API key unset).
    """
    api_hit = _search_via_data_api(query, language=language)
    if api_hit[0]:
        return api_hit

    # When the Data API key is configured, never fall back to yt-dlp / Playwright
    # from cloud hosts — API miss usually means quota or no results.
    if _data_api_configured():
        return None, None

    ytdlp_blocked = False
    try:
        import yt_dlp
    except ImportError:
        logger.warning("yt_dlp_not_installed")
        yt_dlp = None  # type: ignore[assignment]

    if yt_dlp is not None:
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
                ytdlp_blocked = True
                _note_block(str(exc), query=query)
            logger.warning("youtube_search_failed", extra={"error": str(exc), "query": query})

    # Playwright Chromium — same approach as youtube-csv-mapper, used when yt-dlp
    # is blocked or returns no usable hit.
    if settings.youtube_playwright_fallback:
        from app.services.youtube_playwright import search_youtube_playwright

        video_id, views = search_youtube_playwright(query)
        if video_id:
            if ytdlp_blocked:
                _note_ok()
            logger.info(
                "youtube_playwright_hit",
                extra={"query": query, "video_id": video_id},
            )
            return video_id, views

    return None, None


def search_youtube_for_song(song: Song) -> tuple[str | None, int | None]:
    """Try several query shapes via the Data API before giving up."""
    for query in build_search_queries(song):
        video_id, views = _search_youtube_sync(query, language=song.language)
        if video_id:
            return video_id, views
    return None, None


def _fetch_view_count_sync(video_id: str) -> int | None:
    """Load view_count for a known video id."""
    views = _fetch_view_count_data_api(video_id)
    if views is not None:
        return views

    if _data_api_configured():
        return None

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

    video_id, views = await asyncio.to_thread(search_youtube_for_song, song)
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
    source: str = "manual",
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
        video_id, views = await asyncio.to_thread(search_youtube_for_song, song)
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

    _record_resolve_batch(
        source=source,
        attempted=len(songs),
        resolved=resolved,
        failed=failed,
    )
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
