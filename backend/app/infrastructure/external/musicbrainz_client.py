"""Async MusicBrainz API client (rate-limited to 1 req/sec per their policy)."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import quote

import httpx
import structlog

logger = structlog.get_logger()

COMPOSER_REL_TYPES = frozenset(
    {"composer", "writer", "arranger", "lyricist", "author", "librettist"}
)
PERFORMER_REL_TYPES = frozenset(
    {"performer", "vocal", "lead vocals", "background vocals", "singer", "artist"}
)


class MusicBrainzClient:
    BASE_URL = "https://musicbrainz.org/ws/2"

    def __init__(self, user_agent: str, timeout: float = 12.0):
        self._user_agent = user_agent
        self._timeout = timeout
        self._lock = asyncio.Lock()
        self._last_request_at = 0.0

    async def _throttle(self) -> None:
        async with self._lock:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < 1.05:
                await asyncio.sleep(1.05 - elapsed)
            self._last_request_at = time.monotonic()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        await self._throttle()
        url = f"{self.BASE_URL}{path}"
        headers = {"User-Agent": self._user_agent, "Accept": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, params=params, headers=headers)
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
        except Exception:
            logger.exception("musicbrainz_request_failed", path=path)
            return None

    async def search_recording(
        self,
        title: str,
        artist: str | None = None,
        duration_seconds: int | None = None,
        *,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        title = (title or "").strip()
        if not title:
            return []

        clauses = [f'recording:"{title}"']
        if artist and artist.strip():
            clauses.append(f'artist:"{artist.strip()}"')
        if duration_seconds and duration_seconds > 0:
            ms = duration_seconds * 1000
            clauses.append(f"dur:[{max(0, ms - 8000)} TO {ms + 8000}]")

        data = await self._get(
            "/recording",
            {"query": " AND ".join(clauses), "fmt": "json", "limit": limit},
        )
        if not data:
            return []
        return data.get("recordings") or []

    async def lookup_recording(self, mbid: str) -> dict[str, Any] | None:
        return await self._get(
            f"/recording/{quote(mbid)}",
            {
                "inc": "artist-credits+releases+release-groups+work-rels+artist-rels",
                "fmt": "json",
            },
        )

    async def lookup_work(self, mbid: str) -> dict[str, Any] | None:
        return await self._get(
            f"/work/{quote(mbid)}",
            {"inc": "artist-rels", "fmt": "json"},
        )
