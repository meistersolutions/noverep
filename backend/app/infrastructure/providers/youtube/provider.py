import asyncio
import base64
import re
import tempfile
from pathlib import Path
from typing import Any

import structlog
import yt_dlp

from app.config import settings
from app.domain.entities import ProviderTrack
from app.domain.interfaces import MusicProvider
from app.infrastructure.providers.youtube.song_filter import (
    filter_any_video_tracks,
    filter_song_tracks,
    is_single_song_track,
    normalize_search_query,
)
from app.infrastructure.providers.youtube.metadata_utils import (
    fetch_oembed_metadata,
    is_placeholder_youtube_title,
    pick_display_artist,
    pick_display_title,
)

logger = structlog.get_logger()

# Try several YouTube player clients; datacenter IPs often need cookies too.
_AUDIO_CLIENT_ATTEMPTS: list[list[str]] = [
    ["android", "ios"],
    ["tv_embedded", "tv"],
    ["mweb"],
    ["web"],
]


def _youtube_cookiefile() -> str | None:
    """Resolve a Netscape cookies.txt path for yt-dlp (Render-friendly)."""
    file_path = (settings.youtube_cookies_file or "").strip()
    if file_path and Path(file_path).is_file():
        return file_path

    raw = (settings.youtube_cookies or "").strip()
    if not raw and settings.youtube_cookies_b64:
        try:
            raw = base64.b64decode(settings.youtube_cookies_b64).decode("utf-8")
        except Exception:
            logger.warning("youtube_cookies_b64_invalid")
            raw = ""

    if not raw:
        return None

    path = Path(tempfile.gettempdir()) / "noverep_youtube_cookies.txt"
    try:
        path.write_text(raw, encoding="utf-8")
        return str(path)
    except Exception as e:
        logger.warning("youtube_cookies_write_failed", error=str(e))
        return None


def _parse_duration(title: str) -> tuple[str, str]:
    artist = "Unknown Artist"
    song_title = title
    for sep in [" - ", " – ", " | "]:
        if sep in title:
            parts = title.split(sep, 1)
            if len(parts) == 2:
                artist, song_title = parts[0].strip(), parts[1].strip()
                if not artist:
                    artist = "Unknown Artist"
                song_title = re.sub(r"\(official.*?\)", "", song_title, flags=re.I).strip()
                song_title = re.sub(r"\[.*?]", "", song_title).strip()
            break
    if not song_title.strip():
        song_title = title.strip() or "Unknown"
    return artist, song_title


def _is_playable_media_url(url: str | None) -> bool:
    """Reject storyboards/thumbnails that yt-dlp sometimes exposes as format URLs."""
    if not url or not isinstance(url, str):
        return False
    if not url.startswith("http"):
        return False
    lower = url.lower()
    if "storyboard" in lower or "/sb/" in lower:
        return False
    if "ytimg.com" in lower:
        return False
    if any(ext in lower for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")):
        return False
    return True


def _pick_audio_stream(info: dict[str, Any]) -> tuple[str, dict[str, str], str | None]:
    """Pick a real audio (or AV) progressive URL suitable for ExoPlayer."""
    formats = [f for f in (info.get("formats") or []) if isinstance(f, dict)]
    candidates: list[tuple[int, str, dict[str, Any]]] = []

    for fmt in formats:
        url = fmt.get("url")
        if not _is_playable_media_url(url):
            continue
        acodec = fmt.get("acodec")
        if acodec in (None, "none"):
            continue
        # Skip DRM / manifest-only entries without a direct URL protocol we can play
        protocol = (fmt.get("protocol") or "").lower()
        if protocol in ("mhtml", "websocket"):
            continue

        vcodec = fmt.get("vcodec")
        score = int(fmt.get("abr") or fmt.get("tbr") or 0)
        if vcodec in (None, "none"):
            score += 10_000  # prefer audio-only
        ext = (fmt.get("ext") or "").lower()
        if ext in ("m4a", "mp4", "webm", "opus"):
            score += 100
        if "googlevideo.com" in url.lower():
            score += 50
        candidates.append((score, url, fmt))

    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        _score, url, fmt = candidates[0]
        headers = fmt.get("http_headers") or info.get("http_headers") or {}
        mime = fmt.get("ext") or fmt.get("acodec") or info.get("ext")
        return url, {str(k): str(v) for k, v in dict(headers).items() if v is not None}, mime

    # Fallback: top-level url only if it looks like real media
    top = info.get("url")
    if _is_playable_media_url(top):
        headers = info.get("http_headers") or {}
        return (
            top,
            {str(k): str(v) for k, v in dict(headers).items() if v is not None},
            info.get("acodec") or info.get("ext"),
        )

    raise ValueError("No playable audio format found (YouTube returned no direct stream)")


class YouTubeProvider(MusicProvider):
    """YouTube music provider – songs only by default; optional any-video search."""

    SEARCH_BUFFER = 3  # fetch extra to allow filtering

    @property
    def name(self) -> str:
        return "youtube"

    def _ydl_opts(self, extract_flat: bool = True) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": extract_flat,
            "skip_download": True,
            "default_search": "ytsearch",
            "socket_timeout": 20,
        }
        if not extract_flat:
            opts["format"] = "bestaudio/best"
            opts["ignore_no_formats_error"] = True
        return opts

    def _audio_stream_ydl_opts(self, player_clients: list[str]) -> dict[str, Any]:
        """Options tuned for resolving a direct ExoPlayer-compatible audio URL."""
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": 30,
            "extractor_args": {
                "youtube": {
                    "player_client": player_clients,
                }
            },
            "format": (
                "bestaudio[ext=m4a]/bestaudio[acodec!=none][vcodec=none]/"
                "bestaudio/best[acodec!=none]"
            ),
        }
        cookiefile = _youtube_cookiefile()
        if cookiefile:
            opts["cookiefile"] = cookiefile
        return opts

    async def search(
        self,
        query: str,
        limit: int = 20,
        *,
        raw: bool = False,
        songs_only: bool = True,
    ) -> list[ProviderTrack]:
        return await asyncio.to_thread(self._search_sync, query, limit, raw, songs_only)

    def _search_sync(
        self, query: str, limit: int, raw: bool = False, songs_only: bool = True
    ) -> list[ProviderTrack]:
        if songs_only:
            normalized = query.strip() if raw else normalize_search_query(query)
        else:
            normalized = query.strip() or "video"
        fetch_count = min(limit * self.SEARCH_BUFFER, 60)
        search_query = f"ytsearch{fetch_count}:{normalized}"
        collected: list[ProviderTrack] = []

        try:
            with yt_dlp.YoutubeDL(self._ydl_opts()) as ydl:
                info = ydl.extract_info(search_query, download=False)
                entries = info.get("entries", []) if info else []

                for entry in entries:
                    if not entry:
                        continue
                    track = self._entry_to_track(entry, songs_only=songs_only)
                    if track:
                        collected.append(track)
        except Exception as e:
            logger.error("youtube_search_failed", error=str(e), query=query)

        if songs_only:
            return filter_song_tracks(collected, limit)
        return filter_any_video_tracks(collected, limit)

    async def get_metadata(
        self, provider_track_id: str, *, songs_only: bool = True
    ) -> ProviderTrack:
        return await asyncio.to_thread(self._get_metadata_sync, provider_track_id, songs_only)

    async def get_audio_stream(self, provider_track_id: str) -> dict[str, Any]:
        """Resolve a direct audio URL for native ExoPlayer background playback."""
        return await asyncio.to_thread(self._get_audio_stream_sync, provider_track_id)

    def _get_audio_stream_sync(self, provider_track_id: str) -> dict[str, Any]:
        url = f"https://www.youtube.com/watch?v={provider_track_id}"
        last_error: Exception | None = None
        cookiefile = _youtube_cookiefile()

        for clients in _AUDIO_CLIENT_ATTEMPTS:
            try:
                with yt_dlp.YoutubeDL(self._audio_stream_ydl_opts(clients)) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        raise ValueError("No stream info")

                    stream_url, http_headers, mime = _pick_audio_stream(info)

                    title = info.get("title") or f"YouTube {provider_track_id}"
                    artist = (
                        info.get("artist")
                        or info.get("uploader")
                        or info.get("channel")
                        or "Unknown Artist"
                    )
                    duration = info.get("duration")
                    thumbnail = info.get("thumbnail")
                    if not thumbnail and info.get("thumbnails"):
                        thumbnail = info["thumbnails"][-1].get("url")

                    logger.info(
                        "audio_stream_ok",
                        track_id=provider_track_id,
                        clients=clients,
                        cookies=bool(cookiefile),
                    )
                    return {
                        "provider": "youtube",
                        "provider_track_id": provider_track_id,
                        "url": stream_url,
                        "title": title,
                        "artist": artist,
                        "duration_seconds": int(duration) if duration else None,
                        "thumbnail_url": thumbnail,
                        "mime_type": mime or "audio/mp4",
                        "http_headers": http_headers or None,
                    }
            except Exception as e:
                last_error = e
                logger.warning(
                    "audio_stream_client_failed",
                    track_id=provider_track_id,
                    clients=clients,
                    error=str(e),
                    cookies=bool(cookiefile),
                )

        if last_error:
            hint = ""
            err_text = str(last_error).lower()
            if "bot" in err_text or "sign in" in err_text:
                hint = (
                    " YouTube is blocking this server IP. Set YOUTUBE_COOKIES "
                    "(Netscape cookies.txt) on the API host and redeploy."
                )
            raise RuntimeError(f"{last_error}.{hint}") from last_error
        raise ValueError("No stream info")

    def _get_metadata_sync(self, provider_track_id: str, songs_only: bool = True) -> ProviderTrack:
        url = f"https://www.youtube.com/watch?v={provider_track_id}"

        try:
            with yt_dlp.YoutubeDL(self._ydl_opts(extract_flat=False)) as ydl:
                info = ydl.extract_info(url, download=False)
                track = self._entry_to_track(info, full=True, songs_only=songs_only)
                if track and (
                    not songs_only or not is_placeholder_youtube_title(track.title)
                ):
                    return track
        except Exception as e:
            logger.warning("youtube_metadata_full_failed", video_id=provider_track_id, error=str(e))

        oembed = fetch_oembed_metadata(provider_track_id)
        if oembed:
            title, artist = oembed
            return ProviderTrack(
                provider="youtube",
                provider_track_id=provider_track_id,
                title=title,
                artist=artist,
                album=None,
                duration_seconds=None,
                thumbnail_url=f"https://i.ytimg.com/vi/{provider_track_id}/hqdefault.jpg",
                stream_url=url,
                content_kind="video" if not songs_only else "song",
            )

        try:
            with yt_dlp.YoutubeDL(self._ydl_opts(extract_flat=True)) as ydl:
                info = ydl.extract_info(url, download=False)
                track = self._entry_to_track(info, full=True, songs_only=songs_only)
                if track and (
                    not songs_only or not is_placeholder_youtube_title(track.title)
                ):
                    return track
        except Exception as e:
            logger.warning("youtube_metadata_flat_failed", video_id=provider_track_id, error=str(e))

        if oembed:
            title, artist = oembed
        else:
            title, artist = f"YouTube video {provider_track_id}", "Unknown Artist"

        return ProviderTrack(
            provider="youtube",
            provider_track_id=provider_track_id,
            title=title,
            artist=artist,
            album=None,
            duration_seconds=None,
            thumbnail_url=f"https://i.ytimg.com/vi/{provider_track_id}/hqdefault.jpg",
            stream_url=url,
            content_kind="video" if not songs_only else "song",
        )

    def _entry_to_track(
        self,
        entry: dict,
        full: bool = False,
        songs_only: bool = True,
    ) -> ProviderTrack | None:
        video_id = entry.get("id")
        if not video_id:
            return None

        title = entry.get("title", "Unknown")
        artist, song_title = _parse_duration(title)
        duration = entry.get("duration")

        if songs_only:
            if full and not is_single_song_track(title, int(duration) if duration else None):
                return None
            if not full and not is_single_song_track(title, int(duration) if duration else None):
                return None

        thumbnail = entry.get("thumbnail")
        if not thumbnail and entry.get("thumbnails"):
            thumbnail = entry["thumbnails"][-1].get("url")

        display_title = song_title if full and songs_only else title
        release_year = None
        upload_date = entry.get("upload_date") or entry.get("release_date")
        if upload_date and len(str(upload_date)) >= 4:
            try:
                release_year = int(str(upload_date)[:4])
            except ValueError:
                release_year = None

        display_artist = (entry.get("uploader") or entry.get("channel") or artist or "").strip()
        if not display_artist:
            display_artist = "Unknown Artist"
        if not display_title or not str(display_title).strip():
            display_title = title or "Unknown"

        return ProviderTrack(
            provider="youtube",
            provider_track_id=video_id,
            title=str(display_title).strip(),
            artist=display_artist,
            album=None,
            duration_seconds=int(duration) if duration else None,
            thumbnail_url=thumbnail,
            stream_url=f"https://www.youtube.com/watch?v={video_id}",
            popularity=float(entry.get("view_count") or 0) / 1_000_000,
            release_year=release_year,
            content_kind="song" if songs_only else "video",
        )
