"""Synced lyrics via LRCLIB (MusicBrainz does not host lyrics)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

TIMESTAMP_RE = re.compile(r"\[(\d{1,2}):(\d{2}(?:\.\d{1,3})?)\]")


@dataclass
class LyricsLine:
    time_ms: int
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"time_ms": self.time_ms, "text": self.text}


@dataclass
class TrackLyrics:
    synced: bool
    plain: str | None
    lines: list[LyricsLine]
    instrumental: bool = False
    source: str = "lrclib"

    def to_dict(self) -> dict[str, Any]:
        return {
            "synced": self.synced,
            "plain": self.plain,
            "lines": [line.to_dict() for line in self.lines],
            "instrumental": self.instrumental,
            "source": self.source,
        }


def parse_lrc(lrc_content: str) -> list[LyricsLine]:
    if not lrc_content or not lrc_content.strip():
        return []

    lines: list[LyricsLine] = []
    found_synced = False
    for raw_line in lrc_content.replace("\\n", "\n").splitlines():
        trimmed = raw_line.strip()
        if not trimmed:
            continue
        matches = list(TIMESTAMP_RE.finditer(trimmed))
        if matches:
            found_synced = True
            text = trimmed[matches[-1].end() :].strip()
            for match in matches:
                minutes = int(match.group(1))
                seconds = float(match.group(2))
                time_ms = int((minutes * 60 + seconds) * 1000)
                lines.append(LyricsLine(time_ms=time_ms, text=text))
        elif not found_synced:
            lines.append(LyricsLine(time_ms=-1, text=trimmed))

    if not found_synced:
        return [LyricsLine(time_ms=idx * 1000, text=line.text) for idx, line in enumerate(lines)]

    return sorted(lines, key=lambda line: line.time_ms)


class LyricsService:
    BASE_URL = "https://lrclib.net/api"

    def __init__(self, timeout: float = 15.0):
        self._timeout = timeout

    async def fetch_lyrics(
        self,
        title: str,
        artist: str,
        album: str | None = None,
        duration_seconds: int | None = None,
        *,
        cached_only: bool = False,
    ) -> TrackLyrics | None:
        from app.application.services.song_matcher import extract_core_title

        search_title = extract_core_title(title, artist)
        attempts: list[dict[str, str | int]] = [
            {
                "track_name": search_title,
                "artist_name": artist.strip() or "Unknown",
            }
        ]
        if album:
            attempts[0]["album_name"] = album.strip()
        if duration_seconds and duration_seconds > 0:
            attempts[0]["duration"] = duration_seconds

        attempts.append(
            {
                "track_name": search_title,
                "artist_name": artist.strip() or "Unknown",
            }
        )
        if title.strip() and title.strip() != search_title:
            attempts.append(
                {
                    "track_name": title.strip(),
                    "artist_name": artist.strip() or "Unknown",
                }
            )

        endpoint = "/get-cached" if cached_only else "/get"
        for params in attempts:
            result = await self._request_lyrics(endpoint, params)
            if result:
                return result
            if not cached_only:
                result = await self._request_lyrics("/get-cached", params)
                if result:
                    return result

        if not cached_only:
            search_result = await self._search_lyrics(search_title, artist, album)
            if search_result:
                return search_result

        return None

    async def _request_lyrics(
        self, endpoint: str, params: dict[str, str | int]
    ) -> TrackLyrics | None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{self.BASE_URL}{endpoint}", params=params)
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                data = response.json()
        except Exception:
            return None
        return self._parse_payload(data)

    async def _search_lyrics(
        self, title: str, artist: str, album: str | None
    ) -> TrackLyrics | None:
        params: dict[str, str] = {
            "track_name": title,
            "artist_name": artist,
        }
        if album:
            params["album_name"] = album
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{self.BASE_URL}/search", params=params)
                if response.status_code != 200:
                    return None
                items = response.json()
        except Exception:
            logger.exception("lyrics_search_failed", title=title, artist=artist)
            return None

        if not isinstance(items, list) or not items:
            return None
        return self._parse_payload(items[0])

    def _parse_payload(self, data: dict) -> TrackLyrics | None:
        synced_raw = (data.get("syncedLyrics") or "").strip()
        plain_raw = (data.get("plainLyrics") or "").strip()
        instrumental = bool(data.get("instrumental"))

        if synced_raw:
            lines = parse_lrc(synced_raw)
            return TrackLyrics(
                synced=True,
                plain=plain_raw or None,
                lines=lines,
                instrumental=instrumental,
            )

        if plain_raw:
            lines = [
                LyricsLine(time_ms=idx * 3000, text=line.strip())
                for idx, line in enumerate(plain_raw.splitlines())
                if line.strip()
            ]
            return TrackLyrics(synced=False, plain=plain_raw, lines=lines, instrumental=instrumental)

        if instrumental:
            return TrackLyrics(synced=False, plain=None, lines=[], instrumental=True)

        return None
