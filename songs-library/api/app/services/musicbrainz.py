"""MusicBrainz pagination for composer works/songs."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.config import settings

MB_API = "https://musicbrainz.org/ws/2"


def _headers() -> dict[str, str]:
    return {
        "User-Agent": settings.user_agent,
        "Accept": "application/json",
    }


async def resolve_artist_id(name: str) -> tuple[str | None, str | None]:
    async with httpx.AsyncClient(timeout=40.0, headers=_headers()) as client:
        resp = await client.get(
            f"{MB_API}/artist/",
            params={"query": name, "fmt": "json", "limit": 5},
        )
        if resp.status_code == 429:
            await asyncio.sleep(1.5)
            resp = await client.get(
                f"{MB_API}/artist/",
                params={"query": name, "fmt": "json", "limit": 5},
            )
        resp.raise_for_status()
        artists = resp.json().get("artists") or []
    if not artists:
        return None, None
    hit = artists[0]
    return hit.get("id"), hit.get("name")


async def fetch_artist_works(
    artist_id: str,
    *,
    limit: int = 5000,
    page_size: int = 100,
) -> list[dict[str, Any]]:
    """Page through MusicBrainz works for an artist (1 req/sec polite)."""
    out: list[dict[str, Any]] = []
    offset = 0
    async with httpx.AsyncClient(timeout=60.0, headers=_headers()) as client:
        while len(out) < limit:
            resp = await client.get(
                f"{MB_API}/work",
                params={
                    "artist": artist_id,
                    "fmt": "json",
                    "limit": min(page_size, limit - len(out)),
                    "offset": offset,
                },
            )
            if resp.status_code == 429:
                await asyncio.sleep(2.0)
                continue
            resp.raise_for_status()
            payload = resp.json()
            works = payload.get("works") or []
            total = int(payload.get("work-count") or 0)
            for w in works:
                title = (w.get("title") or "").strip()
                if not title:
                    continue
                out.append(
                    {
                        "wikidata_id": None,
                        "musicbrainz_id": w.get("id"),
                        "song_name": title,
                        "movie_name": None,
                        "release_year": None,
                        "singers": [],
                        "lyricists": [],
                        "source": "musicbrainz",
                    }
                )
            offset += len(works)
            if not works or offset >= total:
                break
            await asyncio.sleep(1.05)
    return out[:limit]
