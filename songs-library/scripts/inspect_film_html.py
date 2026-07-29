"""Dump soundtrack-related HTML snippets from a modern film page."""
from __future__ import annotations

import re
import httpx

UA = {
    "User-Agent": "SongsLibrary/0.1 (https://github.com/meistersolutions/noverep; noverep-dev)",
    "Accept": "application/json",
}


def main() -> None:
    for page in ["Dragon (2025 film)", "Parasakthi (2026 film)", "Maareesan"]:
        r = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "parse",
                "page": page,
                "prop": "wikitext|text",
                "format": "json",
                "redirects": 1,
            },
            headers=UA,
            timeout=90,
        )
        j = r.json()
        if "error" in j:
            print(page, j["error"])
            continue
        title = j["parse"]["title"]
        wt = j["parse"]["wikitext"]["*"]
        html = j["parse"]["text"]["*"]
        print("\n====", title, "====")
        # wikitext soundtrack cues
        for m in re.finditer(r"(?i)==+\s*[^=]*(soundtrack|track\s*list|songs?|music)[^=]*==+", wt):
            start = m.start()
            print("SECTION", wt[start : start + 500].replace("\n", " | "))
        # html tables without requiring wikitable
        tables = re.findall(r"<table[^>]*>.*?</table>", html, flags=re.I | re.S)
        print("all tables", len(tables))
        wiki = [t for t in tables if "wikitable" in t.casefold()]
        print("wikitables", len(wiki))
        track = [t for t in tables if "tracklist" in t.casefold() or "song" in t.casefold()[:500]]
        print("songish tables", len(track))
        # look for tracklist template output
        if "tracklist" in html.casefold() or "Track listing" in html:
            idx = html.casefold().find("track")
            print("html snippet", html[max(0, idx - 100) : idx + 800][:900])


if __name__ == "__main__":
    main()
