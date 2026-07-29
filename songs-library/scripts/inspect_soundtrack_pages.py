"""Inspect dedicated soundtrack pages."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

import httpx
from app.services.wikipedia import _WikiPageParser, _tables_to_works

UA = {
    "User-Agent": "SongsLibrary/0.1 (https://github.com/meistersolutions/noverep; noverep-dev)",
    "Accept": "application/json",
}


def main() -> None:
    for page in [
        "Dragon (soundtrack)",
        "Parasakthi (soundtrack)",
        "Maareesan (soundtrack)",
        "Pudhupettai",
    ]:
        r = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "parse",
                "page": page,
                "prop": "text|wikitext",
                "format": "json",
                "redirects": 1,
            },
            headers=UA,
            timeout=90,
        )
        j = r.json()
        if "error" in j:
            print(page, "ERR", j["error"].get("code"))
            continue
        title = j["parse"]["title"]
        html = j["parse"]["text"]["*"]
        wt = j["parse"]["wikitext"]["*"]
        parser = _WikiPageParser()
        parser.feed(html)
        works = _tables_to_works(parser.tables, page_title=title)
        all_tables = re.findall(r"<table[^>]*class=\"([^\"]*)\"", html, flags=re.I)
        print(f"\n{title}: wikitables={len(parser.tables)} parsed={len(works)} table_classes={all_tables[:8]}")
        for w in works[:15]:
            print(" -", w["song_name"])
        # tracklist template in wikitext?
        tracks = re.findall(r"\|\s*title\d+\s*=\s*([^\n|]+)", wt)
        print("wikitext titleN=", len(tracks), tracks[:8])
        if "tracklist" in html.casefold():
            i = html.casefold().find("tracklist")
            print("html", html[i : i + 400].replace("\n", " ")[:400])


if __name__ == "__main__":
    main()
