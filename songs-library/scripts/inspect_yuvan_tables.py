"""Inspect Yuvan discography table shapes for multi-song-per-film rows."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

import httpx
from app.services.wikipedia import _WikiPageParser, _tables_to_works, _header_index

UA = {
    "User-Agent": "SongsLibrary/0.1 (https://github.com/meistersolutions/noverep; noverep-dev)",
    "Accept": "application/json",
}


def main() -> None:
    r = httpx.get(
        "https://en.wikipedia.org/w/api.php",
        params={
            "action": "parse",
            "page": "Yuvan Shankar Raja discography",
            "prop": "text",
            "format": "json",
            "redirects": 1,
        },
        headers=UA,
        timeout=90,
    )
    r.raise_for_status()
    html = r.json()["parse"]["text"]["*"]
    parser = _WikiPageParser()
    parser.feed(html)
    print("tables", len(parser.tables))

    # Find tables that look like song lists
    multi_film = 0
    single_film = 0
    songs_in_one_cell = 0
    sample_multi_cell = []
    for year, grid in parser.tables:
        if len(grid) < 2:
            continue
        idx = _header_index([c.casefold() for c in grid[0]])
        if "song" not in idx:
            continue
        song_i = idx["song"]
        film_i = idx.get("film")
        from collections import Counter

        films = Counter()
        for row in grid[1:]:
            if song_i >= len(row):
                continue
            song = row[song_i].strip()
            film = row[film_i].strip() if film_i is not None and film_i < len(row) else ""
            if not song:
                continue
            films[film] += 1
            # Multiple titles in one cell?
            if re.search(r"\n| / |; |\d+\.", song) or song.count('"') >= 4:
                songs_in_one_cell += 1
                if len(sample_multi_cell) < 5:
                    sample_multi_cell.append((film, song[:120]))
        multi = sum(1 for v in films.values() if v > 1)
        single = sum(1 for v in films.values() if v == 1)
        multi_film += multi
        single_film += single
        if multi or single:
            print(
                f"year={year} rows={len(grid)-1} headers={grid[0][:6]} "
                f"films_multi={multi} films_single={single}"
            )

    works = _tables_to_works(parser.tables, page_title="Yuvan Shankar Raja discography")
    from collections import Counter

    c = Counter((w.get("movie_name") or "?") for w in works)
    print("parsed works", len(works), "movies", len(c))
    print("single-song movies", sum(1 for v in c.values() if v == 1))
    print("multi-song movies", sum(1 for v in c.values() if v > 1))
    print("cells that look multi-song", songs_in_one_cell)
    print("samples", sample_multi_cell)

    # Show one recent table raw rows for a known single like Dragon
    for year, grid in parser.tables:
        for row in grid[1:]:
            joined = " | ".join(row)
            if "Dragon" in joined or "With Love" in joined or "Parasakthi" in joined:
                print("ROW", year, row)


if __name__ == "__main__":
    main()
