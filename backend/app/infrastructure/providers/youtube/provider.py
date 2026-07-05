import asyncio
import re
from typing import Any

import structlog
import yt_dlp

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
