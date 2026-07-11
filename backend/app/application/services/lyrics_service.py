"""Synced lyrics via LRCLIB (MusicBrainz does not host lyrics)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from app.application.services.song_matcher import (
    artist_similarity,
    extract_core_title,
    extract_movie_hint,
    match_score,
    normalize_text,
    title_similarity,
)

logger = structlog.get_logger()

TIMESTAMP_RE = re.compile(r"\[(\d{1,2}):(\d{2}(?:\.\d{1,3})?)\]")
LYRICS_MATCH_THRESHOLD = 0.72


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


def _item_field(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value and str(value).strip():
            return str(value).strip()
    return ""


def _item_duration(item: dict[str, Any]) -> int | None:
    raw = item.get("duration")
    if raw is None:
        return None
    try:
        duration = int(raw)
    except (TypeError, ValueError):
        return None
    return duration if duration > 0 else None


def _album_match_score(album_hint: str | None, album_name: str) -> float:
    if not album_hint or not album_name:
        return 0.0
    hint = normalize_text(album_hint)
    norm_album = normalize_text(album_name)
    if hint == norm_album:
        return 1.0
    if hint in norm_album or norm_album in hint:
        return 0.85
    return 0.0


def lyrics_item_score(
    item: dict[str, Any],
    title: str,
    artist: str,
    duration_seconds: int | None,
    album_hint: str | None = None,
) -> float:
    cand_title = _item_field(item, "trackName", "name")
    cand_artist = _item_field(item, "artistName", "artist")
    cand_album = _item_field(item, "albumName", "album")
    cand_duration = _item_duration(item)

    if not cand_title:
        return 0.0

    score = match_score(
        title,
        artist,
        duration_seconds,
        cand_title,
        cand_artist,
        cand_duration,
    )
    score += _album_match_score(album_hint, cand_album) * 0.15

    if normalize_text(title) != normalize_text(cand_title):
        if artist_similarity(artist, cand_artist) < 0.45:
            return 0.0
        if title_similarity(title, cand_title, artist, cand_artist) < 0.8:
            return 0.0

    return score


def pick_best_lyrics_item(
    items: list[dict[str, Any]],
    title: str,
    artist: str,
    duration_seconds: int | None,
    album_hint: str | None = None,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = 0.0

    for item in items:
        score = lyrics_item_score(item, title, artist, duration_seconds, album_hint)
        if score > best_score:
            best_score = score
            best = item

    return best if best_score >= LYRICS_MATCH_THRESHOLD else None


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
        core_title = extract_core_title(title, artist)
        album_hint = album or extract_movie_hint(title, artist, album)
        artist_name = artist.strip() or "Unknown"

        attempts: list[dict[str, str | int]] = []
        base = {"track_name": core_title, "artist_name": artist_name}
        if album_hint:
            attempts.append({**base, "album_name": album_hint})
        if duration_seconds and duration_seconds > 0:
            with_duration = {**base, "duration": duration_seconds}
            if album_hint:
                with_duration["album_name"] = album_hint
            attempts.append(with_duration)
        attempts.append(base)

        endpoint = "/get-cached" if cached_only else "/get"
        for params in attempts:
            result = await self._request_lyrics(
                endpoint,
                params,
                core_title,
                artist,
                duration_seconds,
                album_hint,
            )
            if result:
                return result
            if not cached_only:
                result = await self._request_lyrics(
                    "/get-cached",
                    params,
                    core_title,
                    artist,
                    duration_seconds,
                    album_hint,
                )
                if result:
                    return result

        if not cached_only:
            search_result = await self._search_lyrics(
                core_title,
                artist,
                album_hint,
                duration_seconds,
            )
            if search_result:
                return search_result

            # Broader LRCLIB query (title + artist as free text).
            q_result = await self._search_lyrics_q(core_title, artist_name, duration_seconds, album_hint)
            if q_result:
                return q_result

            # Plain-text fallback when synced providers miss (common for regional music).
            ovh = await self._fetch_lyrics_ovh(core_title, artist_name)
            if ovh:
                return ovh

        return None

    async def _search_lyrics_q(
        self,
        title: str,
        artist: str,
        duration_seconds: int | None,
        album_hint: str | None,
    ) -> TrackLyrics | None:
        query = f"{title} {artist}".strip()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    f"{self.BASE_URL}/search",
                    params={"q": query},
                )
                if response.status_code != 200:
                    return None
                items = response.json()
        except Exception:
            return None

        if not isinstance(items, list) or not items:
            return None

        picked = pick_best_lyrics_item(items, title, artist, duration_seconds, album_hint)
        if not picked:
            # Accept a looser top hit when duration is close.
            scored = [
                (lyrics_item_score(item, title, artist, duration_seconds, album_hint), item)
                for item in items
            ]
            scored.sort(key=lambda pair: pair[0], reverse=True)
            if scored and scored[0][0] >= 0.55:
                picked = scored[0][1]
            else:
                return None
        return self._parse_payload(picked)

    async def _fetch_lyrics_ovh(self, title: str, artist: str) -> TrackLyrics | None:
        """Fallback plain lyrics from lyrics.ovh (no sync timestamps)."""
        if not title or not artist or artist == "Unknown":
            return None
        from urllib.parse import quote

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    f"https://api.lyrics.ovh/v1/{quote(artist)}/{quote(title)}",
                )
                if response.status_code != 200:
                    return None
                data = response.json()
        except Exception:
            return None

        plain = (data.get("lyrics") or "").strip() if isinstance(data, dict) else ""
        if not plain or len(plain) < 40:
            return None

        lines = [
            LyricsLine(time_ms=idx * 3000, text=line.strip())
            for idx, line in enumerate(plain.splitlines())
            if line.strip() and not line.strip().startswith("Paroles de la chanson")
        ]
        if len(lines) < 4:
            return None

        return TrackLyrics(
            synced=False,
            plain=plain,
            lines=lines,
            instrumental=False,
            source="lyrics.ovh",
        )

    async def _request_lyrics(
        self,
        endpoint: str,
        params: dict[str, str | int],
        title: str,
        artist: str,
        duration_seconds: int | None,
        album_hint: str | None,
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

        if not isinstance(data, dict):
            return None

        score = lyrics_item_score(data, title, artist, duration_seconds, album_hint)
        if score < LYRICS_MATCH_THRESHOLD:
            return None

        return self._parse_payload(data)

    async def _search_lyrics(
        self,
        title: str,
        artist: str,
        album_hint: str | None,
        duration_seconds: int | None,
    ) -> TrackLyrics | None:
        params: dict[str, str] = {
            "track_name": title,
            "artist_name": artist,
        }
        if album_hint:
            params["album_name"] = album_hint
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

        picked = pick_best_lyrics_item(items, title, artist, duration_seconds, album_hint)
        if not picked:
            return None
        return self._parse_payload(picked)

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
