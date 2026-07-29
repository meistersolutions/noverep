"""HTTP client for the standalone Songs Library service."""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()


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


class SongsLibraryClient:
    def __init__(self, base_url: str | None = None, timeout: float = 45.0):
        self.base_url = (base_url or settings.songs_library_url or "").rstrip("/")
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(settings.songs_library_enabled and self.base_url)

    async def health(self) -> bool:
        if not self.enabled:
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.base_url}/api/health")
                return resp.status_code == 200
        except Exception as exc:  # noqa: BLE001
            logger.warning("songs_library_health_failed", error=str(exc))
            return False

    async def sample(
        self,
        *,
        composer: str | None = None,
        seed: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        moods: list[str] | None = None,
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
            "moods": moods or [],
            "exclude_hashes": exclude_hashes or [],
            "exclude_ids": exclude_ids or [],
            "only_mapped": only_mapped,
            "limit": limit,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}/api/sample", json=payload)
                resp.raise_for_status()
                data = resp.json()
            return [LibrarySong.from_dict(row) for row in data]
        except Exception as exc:  # noqa: BLE001
            logger.warning("songs_library_sample_failed", error=str(exc), seed=seed or composer)
            return []

    async def discover(self, seeds: list[str], limit_per_seed: int | None = None) -> dict:
        if not self.enabled or not seeds:
            return {"results": [], "total_inserted": 0, "total_skipped": 0}
        payload: dict = {"seeds": seeds}
        if limit_per_seed is not None:
            payload["limit_per_seed"] = limit_per_seed
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(f"{self.base_url}/api/discover", json=payload)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("songs_library_discover_failed", error=str(exc), seeds=seeds)
            return {"results": [], "total_inserted": 0, "total_skipped": 0, "error": str(exc)}

    async def resolve_youtube_for_song(self, song_id: str) -> LibrarySong | None:
        """Playback-only YouTube mapping for a catalog song (not discovery)."""
        if not self.enabled or not song_id:
            return None
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(f"{self.base_url}/api/songs/{song_id}/resolve-youtube")
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.json()
            return LibrarySong.from_dict(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "songs_library_resolve_youtube_failed",
                error=str(exc),
                song_id=song_id,
            )
            return None
