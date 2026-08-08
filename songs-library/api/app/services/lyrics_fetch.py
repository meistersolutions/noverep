"""Fetch plain lyrics for enrichment (LRCLIB, then lyrics.ovh)."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import httpx

from app.config import settings

LRCLIB_BASE = "https://lrclib.net/api"


@dataclass
class LyricsResult:
    text: str
    source: str
    instrumental: bool = False


def _join_people(people: list | None) -> str:
    if not people:
        return ""
    return ", ".join(str(p).strip() for p in people if str(p).strip())


def artist_for_lyrics(song) -> str:
    singers = _join_people(getattr(song, "singers", None))
    if singers:
        # LRCLIB matches better on a primary artist name.
        return singers.split(",")[0].strip()
    return (getattr(song, "composer_name", None) or "").strip() or "Unknown"


async def fetch_lyrics_for_song(song) -> LyricsResult | None:
    title = (song.song_name or "").strip()
    if not title:
        return None
    artist = artist_for_lyrics(song)
    album = (song.movie_name or "").strip() or None

    result = await _lrclib_get(title, artist, album)
    if result:
        return result
    result = await _lrclib_search(title, artist, album)
    if result:
        return result
    if artist and artist != "Unknown":
        result = await _lyrics_ovh(title, artist)
        if result:
            return result
    return None


async def _lrclib_get(title: str, artist: str, album: str | None) -> LyricsResult | None:
    params: dict[str, str] = {"track_name": title, "artist_name": artist}
    if album:
        params["album_name"] = album
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            for endpoint in ("/get", "/get-cached"):
                response = await client.get(f"{LRCLIB_BASE}{endpoint}", params=params)
                if response.status_code == 404:
                    continue
                if response.status_code != 200:
                    continue
                data = response.json()
                parsed = _parse_lrclib(data)
                if parsed:
                    return parsed
    except Exception:  # noqa: BLE001
        return None
    return None


async def _lrclib_search(title: str, artist: str, album: str | None) -> LyricsResult | None:
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"{LRCLIB_BASE}/search",
                params={"q": f"{title} {artist}".strip()},
            )
            if response.status_code != 200:
                return None
            items = response.json()
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(items, list) or not items:
        return None
    title_l = title.casefold()
    artist_l = artist.casefold()
    best = None
    best_score = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        t = str(item.get("trackName") or "").casefold()
        a = str(item.get("artistName") or "").casefold()
        score = 0
        if t == title_l:
            score += 3
        elif title_l in t or t in title_l:
            score += 2
        if artist_l and (artist_l in a or a in artist_l):
            score += 2
        if album:
            al = str(item.get("albumName") or "").casefold()
            if album.casefold() in al or al in album.casefold():
                score += 1
        if score > best_score:
            best_score = score
            best = item
    if not best or best_score < 2:
        return None
    return _parse_lrclib(best)


def _parse_lrclib(data: dict) -> LyricsResult | None:
    if bool(data.get("instrumental")):
        return LyricsResult(text="", source="lrclib", instrumental=True)
    plain = (data.get("plainLyrics") or "").strip()
    synced = (data.get("syncedLyrics") or "").strip()
    if plain:
        text = plain
    elif synced:
        lines = []
        for raw in synced.replace("\\n", "\n").splitlines():
            line = raw.strip()
            if not line:
                continue
            if "]" in line:
                line = line.split("]", 1)[-1].strip()
            if line:
                lines.append(line)
        text = "\n".join(lines)
    else:
        return None
    text = text.strip()
    if len(text) < 20:
        return None
    max_chars = settings.lyrics_max_chars
    if len(text) > max_chars:
        text = text[:max_chars]
    return LyricsResult(text=text, source="lrclib")


async def _lyrics_ovh(title: str, artist: str) -> LyricsResult | None:
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"https://api.lyrics.ovh/v1/{quote(artist)}/{quote(title)}"
            )
            if response.status_code != 200:
                return None
            data = response.json()
    except Exception:  # noqa: BLE001
        return None
    plain = (data.get("lyrics") or "").strip() if isinstance(data, dict) else ""
    if not plain or len(plain) < 40:
        return None
    lines = [
        line.strip()
        for line in plain.splitlines()
        if line.strip() and not line.strip().startswith("Paroles de la chanson")
    ]
    if len(lines) < 4:
        return None
    text = "\n".join(lines)
    max_chars = settings.lyrics_max_chars
    if len(text) > max_chars:
        text = text[:max_chars]
    return LyricsResult(text=text, source="lyrics.ovh")
