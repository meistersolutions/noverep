"""Wikipedia HTML discovery for composer song lists / discographies."""

from __future__ import annotations

import asyncio
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote

import httpx

from app.config import settings

WIKI_API = "https://en.wikipedia.org/w/api.php"


def _headers() -> dict[str, str]:
    return {
        "User-Agent": settings.user_agent,
        "Accept": "application/json",
    }


def _clean_cell(text: str) -> str:
    text = re.sub(r"\[[^\]]*\]", "", text)  # strip [1] refs
    text = text.replace("\xa0", " ").strip()
    text = text.strip("\"'“”‘’")
    return re.sub(r"\s+", " ", text)


def _year_from_heading(text: str) -> int | None:
    m = re.search(r"\b((?:19|20)\d{2})\b", text or "")
    if not m:
        return None
    return int(m.group(1))


class _WikiPageParser(HTMLParser):
    """Parse page HTML: track year headings + wikitables (with rowspan)."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[tuple[int | None, list[list[str]]]] = []
        self._current_year: int | None = None
        self._in_heading = False
        self._heading_parts: list[str] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._cell_parts: list[str] = []
        self._cell_rowspan = 1
        self._cell_colspan = 1
        self._current_row: list[tuple[str, int, int]] = []
        self._occupancy: list[list[str | None]] = []
        self._row_idx = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k: (v or "") for k, v in attrs}
        if tag in ("h2", "h3", "h4") and not self._in_table:
            self._in_heading = True
            self._heading_parts = []
            return
        if tag == "table" and "wikitable" in ad.get("class", ""):
            self._in_table = True
            self._occupancy = []
            self._row_idx = 0
            return
        if not self._in_table:
            return
        if tag == "tr":
            self._in_row = True
            self._current_row = []
        elif tag in ("td", "th"):
            self._in_cell = True
            self._cell_parts = []
            try:
                self._cell_rowspan = max(1, int(ad.get("rowspan") or "1"))
            except ValueError:
                self._cell_rowspan = 1
            try:
                self._cell_colspan = max(1, int(ad.get("colspan") or "1"))
            except ValueError:
                self._cell_colspan = 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("h2", "h3", "h4") and self._in_heading:
            heading = _clean_cell("".join(self._heading_parts))
            year = _year_from_heading(heading)
            if year:
                self._current_year = year
            self._in_heading = False
            return
        if tag == "table" and self._in_table:
            self._flush_table()
            self._in_table = False
            return
        if not self._in_table:
            return
        if tag == "tr" and self._in_row:
            self._commit_row()
            self._in_row = False
        elif tag in ("td", "th") and self._in_cell:
            text = _clean_cell("".join(self._cell_parts))
            self._current_row.append((text, self._cell_rowspan, self._cell_colspan))
            self._in_cell = False

    def handle_data(self, data: str) -> None:
        if self._in_heading:
            self._heading_parts.append(data)
        elif self._in_cell:
            self._cell_parts.append(data)

    def _commit_row(self) -> None:
        while len(self._occupancy) <= self._row_idx:
            self._occupancy.append([])
        row_cells: list[str | None] = list(self._occupancy[self._row_idx])
        col = 0
        for text, rowspan, colspan in self._current_row:
            while col < len(row_cells) and row_cells[col] is not None:
                col += 1
            for c in range(colspan):
                idx = col + c
                while len(row_cells) <= idx:
                    row_cells.append(None)
                row_cells[idx] = text if c == 0 else ""
                for r in range(1, rowspan):
                    while len(self._occupancy) <= self._row_idx + r:
                        self._occupancy.append([])
                    target = self._occupancy[self._row_idx + r]
                    while len(target) <= idx:
                        target.append(None)
                    if target[idx] is None:
                        target[idx] = text if c == 0 else ""
            col += colspan
        self._occupancy[self._row_idx] = row_cells
        self._row_idx += 1

    def _flush_table(self) -> None:
        grid: list[list[str]] = []
        for row in self._occupancy:
            if not row:
                continue
            cleaned = [(_clean_cell(c) if c else "") for c in row]
            if any(cleaned):
                grid.append(cleaned)
        if grid:
            self.tables.append((self._current_year, grid))


def _header_index(headers: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for i, h in enumerate(headers):
        key = h.casefold().strip()
        if key in ("song", "song title", "title", "track"):
            mapping.setdefault("song", i)
        elif key in ("film", "movie", "album", "film / album", "film/album"):
            mapping.setdefault("film", i)
        elif key in ("year", "release year"):
            mapping.setdefault("year", i)
        elif "singer" in key or key in ("artist", "performer", "vocalist"):
            mapping.setdefault("singer", i)
        elif "lyric" in key:
            mapping.setdefault("lyricist", i)
    return mapping


def _tables_to_works(
    tables: list[tuple[int | None, list[list[str]]]],
    *,
    page_title: str,
) -> list[dict[str, Any]]:
    works: list[dict[str, Any]] = []
    for default_year, grid in tables:
        if len(grid) < 2:
            continue
        headers = [c.casefold() for c in grid[0]]
        idx = _header_index(headers)
        start = 1
        if "song" not in idx:
            if len(grid[0]) >= 2 and not any(
                h in ("film", "song", "year", "album", "title") for h in headers
            ):
                idx = {"film": 0, "song": 1}
                start = 0
            else:
                continue

        song_i = idx["song"]
        film_i = idx.get("film")
        year_i = idx.get("year")
        singer_i = idx.get("singer")
        lyric_i = idx.get("lyricist")

        for row in grid[start:]:
            if song_i >= len(row):
                continue
            song = row[song_i].strip()
            if not song or song.casefold() in ("song", "title", "track"):
                continue
            if song.startswith("http"):
                continue
            film = row[film_i].strip() if film_i is not None and film_i < len(row) else None
            year = default_year
            if year_i is not None and year_i < len(row):
                year = _year_from_heading(row[year_i]) or year
            singers: list[str] = []
            if singer_i is not None and singer_i < len(row) and row[singer_i].strip():
                singers = [s.strip() for s in re.split(r"[,;/&]| and ", row[singer_i]) if s.strip()]
            lyricists: list[str] = []
            if lyric_i is not None and lyric_i < len(row) and row[lyric_i].strip():
                lyricists = [s.strip() for s in re.split(r"[,;/&]| and ", row[lyric_i]) if s.strip()]
            works.append(
                {
                    "wikidata_id": None,
                    "song_name": song,
                    "movie_name": film or None,
                    "release_year": year,
                    "singers": singers,
                    "lyricists": lyricists,
                    "wikipedia_title": page_title,
                    "source": "wikipedia",
                }
            )
    return works


async def _wiki_get(client: httpx.AsyncClient, params: dict[str, Any]) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            resp = await client.get(WIKI_API, params=params)
            if resp.status_code == 429:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            await asyncio.sleep(1.0 * (attempt + 1))
    if last_exc:
        raise last_exc
    return {}


async def _page_exists(client: httpx.AsyncClient, title: str) -> str | None:
    data = await _wiki_get(
        client,
        {
            "action": "query",
            "titles": title,
            "redirects": 1,
            "format": "json",
        },
    )
    pages = (data.get("query") or {}).get("pages") or {}
    for page in pages.values():
        if page.get("missing") is not None:
            return None
        return page.get("title")
    return None


async def _resolve_song_list_pages(client: httpx.AsyncClient, label: str) -> list[str]:
    candidates = [
        f"List of songs recorded by {label}",
        f"List of songs composed by {label}",
        f"{label} discography",
        f"{label} filmography",
    ]
    found: list[str] = []
    for title in candidates:
        resolved = await _page_exists(client, title)
        if resolved and resolved not in found:
            found.append(resolved)

    data = await _wiki_get(
        client,
        {
            "action": "opensearch",
            "search": f"{label} songs",
            "limit": 8,
            "format": "json",
        },
    )
    titles = data[1] if isinstance(data, list) and len(data) > 1 else []
    first = label.casefold().split()[0]
    for title in titles:
        t = str(title)
        low = t.casefold()
        if first not in low:
            continue
        if any(token in low for token in ("song", "discography", "soundtrack")):
            if t not in found:
                found.append(t)
    return found


def _extract_main_article_links(html: str) -> list[str]:
    links = re.findall(
        r'class="hatnote[^"]*"[^>]*>.*?href="/wiki/([^"#]+)"',
        html,
        flags=re.I | re.S,
    )
    return [unquote(link.replace("_", " ")) for link in links]


async def _parse_page_works(
    client: httpx.AsyncClient,
    title: str,
    *,
    depth: int = 0,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    data = await _wiki_get(
        client,
        {
            "action": "parse",
            "page": title,
            "prop": "text",
            "format": "json",
            "redirects": 1,
            "disableeditsection": 1,
        },
    )
    if "error" in data:
        return []
    parsed = data.get("parse") or {}
    html = (parsed.get("text") or {}).get("*") or ""
    page_title = parsed.get("title") or title

    parser = _WikiPageParser()
    parser.feed(html)
    works = _tables_to_works(parser.tables, page_title=page_title)

    if not works and depth < 1:
        for link in _extract_main_article_links(html)[:6]:
            works.extend(
                await _parse_page_works(client, link, depth=depth + 1, limit=limit)
            )
            if limit and len(works) >= limit:
                return works[:limit]

    if depth < 1 and "discography" in page_title.casefold() and len(works) < 10:
        for link in _extract_main_article_links(html):
            if link == page_title:
                continue
            works.extend(
                await _parse_page_works(client, link, depth=depth + 1, limit=limit)
            )
            if limit and len(works) >= limit:
                return works[:limit]

    return works[:limit] if limit else works


def _dedupe_works(works: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for w in works:
        name = (w.get("song_name") or "").strip()
        if not name:
            continue
        key = (name.casefold(), (w.get("movie_name") or "").strip().casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(w)
    return out


async def fetch_composer_songs(label: str, limit: int) -> list[dict[str, Any]]:
    """Discover songs from English Wikipedia list / discography pages."""
    target = max(limit * 2, limit)
    async with httpx.AsyncClient(timeout=90.0, headers=_headers()) as client:
        pages = await _resolve_song_list_pages(client, label)
        pages.sort(
            key=lambda t: (
                0 if "list of songs" in t.casefold() else 1,
                0 if "discography" in t.casefold() else 1,
                t,
            )
        )
        all_works: list[dict[str, Any]] = []
        for title in pages:
            try:
                all_works.extend(
                    await _parse_page_works(client, title, limit=target - len(all_works))
                )
            except Exception:  # noqa: BLE001
                continue
            if len(all_works) >= target:
                break
    return _dedupe_works(all_works)[:limit]
