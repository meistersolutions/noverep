"""iTunes Search API — free metadata fallback (no API key)."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

logger = structlog.get_logger()


class ITunesClient:
    BASE_URL = "https://itunes.apple.com/search"

    def __init__(self, timeout: float = 12.0):
        self._timeout = timeout

    async def search_song(
        self,
        title: str,
        artist: str | None = None,
        *,
        limit: int = 8,
        country: str = "in",
    ) -> list[dict[str, Any]]:
        term = f"{title} {artist or ''}".strip()
        if not term:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    self.BASE_URL,
                    params={
                        "term": term,
                        "media": "music",
                        "entity": "song",
                        "limit": limit,
                        "country": country,
                    },
                )
                if response.status_code != 200:
                    return []
                data = response.json()
        except Exception:
            logger.exception("itunes_search_failed", term=term)
            return []

        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            return []
        return [item for item in results if isinstance(item, dict)]
