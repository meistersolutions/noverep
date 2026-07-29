"""Check whether film pages expose multi-song soundtrack tables we fail to parse."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

import asyncio
import httpx
from app.services.wikipedia import (
    _WikiPageParser,
    _tables_to_works,
    fetch_film_soundtrack_songs,
    list_composer_films,
)

UA = {
    "User-Agent": "SongsLibrary/0.1 (https://github.com/meistersolutions/noverep; noverep-dev)",
    "Accept": "application/json",
}


async def inspect_film(title: str) -> None:
    r = httpx.get(
        "https://en.wikipedia.org/w/api.php",
        params={"action": "parse", "page": title, "prop": "text", "format": "json", "redirects": 1},
        headers=UA,
        timeout=90,
    )
    data = r.json()
    if "error" in data:
        print(title, "ERR", data["error"])
        return
    html = data["parse"]["text"]["*"]
    resolved = data["parse"]["title"]
    parser = _WikiPageParser()
    parser.feed(html)
    print(f"\n=== {resolved} tables={len(parser.tables)} ===")
    for year, grid in parser.tables:
        headers = grid[0] if grid else []
        print(f"  year={year} rows={max(len(grid)-1,0)} headers={headers[:8]}")
    works = _tables_to_works(parser.tables, page_title=resolved)
    print(f"  parsed soundtrack songs={len(works)}")
    for w in works[:12]:
        print("   -", w["song_name"], "|", w.get("movie_name"))


async def main() -> None:
    for title in [
        "Dragon (2025 film)",
        "Parasakthi (2026 film)",
        "With Love (2026 film)",
        "Junior Senior",
        "Pudhupettai",
    ]:
        await inspect_film(title)

    works, page = await fetch_film_soundtrack_songs("Dragon")
    print("\nfetch_film_soundtrack_songs('Dragon')", page, len(works))

    films, pages = await list_composer_films("Yuvan Shankar Raja")
    names = {(f.get("film") or "").casefold() for f in films}
    for probe in ["dragon", "parasakthi", "with love", "junior senior", "pudhupettai"]:
        print("in film list?", probe, any(probe in n for n in names))
    print("film list size", len(films), "pages", pages[:5])


if __name__ == "__main__":
    asyncio.run(main())
