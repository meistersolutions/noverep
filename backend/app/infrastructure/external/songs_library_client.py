"""HTTP client for the standalone Songs Library service."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()

# Cap concurrent yt-dlp resolves so queue fill does not stampede YouTube.
RESOLVE_YOUTUBE_CONCURRENCY = 5


@dataclass
class LibrarySong:
    id: str
    song_name: str
    movie_name: str | None = None
    release_year: int | None = None
    composer_name: str | None = None
    singers: list[str] = field(default_factory=list)
    lyricists: list[str] = field(default_factory=list)
    popularity: float = 50.0
    moods: list[str] = field(default_factory=list)
    content_hash: str = ""
    youtube_video_id: str | None = None
    playability: str = "metadata_only"

    @classmethod
    def from_dict(cls, data: dict) -> "LibrarySong":
        return cls(
            id=str(data.get("id") or ""),
            song_name=str(data.get("song_name") or ""),
            movie_name=data.get("movie_name"),
            release_year=data.get("release_year"),
            composer_name=data.get("composer_name"),
            singers=list(data.get("singers") or []),
            lyricists=list(data.get("lyricists") or []),
            popularity=float(data.get("popularity") or 50.0),
            moods=list(data.get("moods") or []),
            content_hash=str(data.get("content_hash") or ""),
            youtube_video_id=data.get("youtube_video_id"),
            playability=str(data.get("playability") or "metadata_only"),
        )

    def search_query(self) -> str:
        parts = [self.song_name]
        if self.movie_name:
            parts.append(self.movie_name)
        if self.composer_name:
            parts.append(self.composer_name)
        parts.append("official audio")
        return " ".join(p for p in parts if p)


# Render free-tier cold starts often return 502/503 on the first hit.
_RETRYABLE_STATUS = {502, 503, 504}
_MAX_RETRIES = 3


class SongsLibraryClient:
    def __init__(self, base_url: str | None = None, timeout: float = 60.0):
        self.base_url = (base_url or settings.songs_library_url or "").rstrip("/")
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(settings.songs_library_enabled and self.base_url)

    async def health(self) -> bool:
        if not self.enabled:
            return False
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self.base_url}/api/health")
                return resp.status_code == 200
        except Exception as exc:  # noqa: BLE001
            logger.warning("songs_library_health_failed", error=str(exc))
            return False

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        timeout: float | None = None,
        accept_statuses: frozenset[int] | None = None,
    ) -> httpx.Response | None:
        """HTTP call with retries for Render cold-start 502/503."""
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=timeout or self.timeout) as client:
                    if attempt == 0:
                        # Wake the free-tier instance before the real call.
                        try:
                            await client.get(f"{self.base_url}/api/health")
                        except Exception:  # noqa: BLE001
                            pass
                    resp = await client.request(method, url, json=json)
                if accept_statuses and resp.status_code in accept_statuses:
                    return resp
                if resp.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                resp.raise_for_status()
                return resp
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                raise
        if last_exc:
            raise last_exc
        return None

    async def sample(
        self,
        *,
        composer: str | None = None,
        seed: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        popularity_min: float | None = None,
        popularity_max: float | None = None,
        moods: list[str] | None = None,
        languages: list[str] | None = None,
        exclude_hashes: list[str] | None = None,
        exclude_ids: list[str] | None = None,
        only_mapped: bool = False,
        limit: int = 20,
    ) -> list[LibrarySong]:
        if not self.enabled:
            return []
        payload = {
            "composer": composer,
            "seed": seed,
            "year_from": year_from,
            "year_to": year_to,
            "popularity_min": popularity_min,
            "popularity_max": popularity_max,
            "moods": moods or [],
            "languages": languages or [],
            "exclude_hashes": exclude_hashes or [],
            "exclude_ids": exclude_ids or [],
            "only_mapped": only_mapped,
            "limit": limit,
        }
        try:
            resp = await self._request("POST", "/api/sample", json=payload)
            if not resp:
                return []
            data = resp.json()
            return [LibrarySong.from_dict(row) for row in data]
        except Exception as exc:  # noqa: BLE001
            logger.warning("songs_library_sample_failed", error=str(exc), seed=seed or composer)
            return []

    async def discover(
        self,
        seeds: list[str],
        limit_per_seed: int | None = None,
        *,
        force: bool = False,
    ) -> dict:
        if not self.enabled or not seeds:
            return {"results": [], "total_inserted": 0, "total_skipped": 0}
        payload: dict = {"seeds": seeds, "force": force}
        if limit_per_seed is not None:
            payload["limit_per_seed"] = limit_per_seed
        try:
            resp = await self._request("POST", "/api/discover", json=payload, timeout=120.0)
            if not resp:
                return {"results": [], "total_inserted": 0, "total_skipped": 0}
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("songs_library_discover_failed", error=str(exc), seeds=seeds)
            return {"results": [], "total_inserted": 0, "total_skipped": 0, "error": str(exc)}

    async def resolve_youtube_for_song(self, song_id: str) -> LibrarySong | None:
        """Playback-only YouTube mapping for a catalog song (not discovery)."""
        if not self.enabled or not song_id:
            return None
        try:
            resp = await self._request(
                "POST",
                f"/api/songs/{song_id}/resolve-youtube",
                timeout=60.0,
                accept_statuses=frozenset({404, 422}),
            )
            if not resp or resp.status_code in {404, 422}:
                return None
            return LibrarySong.from_dict(resp.json())
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "songs_library_resolve_youtube_failed",
                error=str(exc),
                song_id=song_id,
            )
            return None

    async def resolve_youtube_many(
        self,
        song_ids: list[str],
        *,
        concurrency: int = RESOLVE_YOUTUBE_CONCURRENCY,
    ) -> dict[str, LibrarySong]:
        """Resolve YouTube ids for many catalog songs in parallel.

        Returns a map of song_id -> LibrarySong for songs that resolved successfully.
        Unresolvable songs are omitted (callers should skip them).
        """
        if not self.enabled or not song_ids:
            return {}
        unique_ids = list(dict.fromkeys(sid for sid in song_ids if sid))
        if not unique_ids:
            return {}

        sem = asyncio.Semaphore(max(1, concurrency))
        resolved: dict[str, LibrarySong] = {}

        async def _one(song_id: str) -> None:
            async with sem:
                song = await self.resolve_youtube_for_song(song_id)
            if song and song.youtube_video_id:
                resolved[song_id] = song

        await asyncio.gather(*(_one(sid) for sid in unique_ids))
        return resolved

    async def export_playlist(self, payload: dict) -> dict:
        """Export mapped songs as a YouTube playlist payload (P4 foundation)."""
        if not self.enabled:
            return {"item_count": 0, "items": []}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}/api/playlists/export", json=payload)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("songs_library_export_playlist_failed", error=str(exc))
            return {"item_count": 0, "items": [], "error": str(exc)}
