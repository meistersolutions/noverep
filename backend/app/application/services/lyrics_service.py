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
        params: dict[str, str | int] = {
            "track_name": title.strip() or "Unknown",
            "artist_name": artist.strip() or "Unknown",
        }
        if album:
            params["album_name"] = album.strip()
        if duration_seconds and duration_seconds > 0:
            params["duration"] = duration_seconds

        endpoint = "/get-cached" if cached_only else "/get"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{self.BASE_URL}{endpoint}", params=params)
                if response.status_code == 404:
                    if not cached_only:
                        return await self.fetch_lyrics(
                            title,
                            artist,
                            album,
                            duration_seconds,
                            cached_only=True,
                        )
                    return None
                response.raise_for_status()
                data = response.json()
        except Exception:
            logger.exception("lyrics_fetch_failed", title=title, artist=artist)
            return None

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
