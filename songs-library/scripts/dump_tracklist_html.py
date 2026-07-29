"""Print one tracklist table HTML structure."""
from __future__ import annotations

import re
import httpx

UA = {
    "User-Agent": "SongsLibrary/0.1 (https://github.com/meistersolutions/noverep; noverep-dev)",
    "Accept": "application/json",
}

r = httpx.get(
    "https://en.wikipedia.org/w/api.php",
    params={
        "action": "parse",
        "page": "Dragon (soundtrack)",
        "prop": "text",
        "format": "json",
        "redirects": 1,
    },
    headers=UA,
    timeout=90,
)
html = r.json()["parse"]["text"]["*"]
# Grab first table with class tracklist that looks like songs
m = re.search(
    r'(<table[^>]*class="[^"]*tracklist[^"]*"[^>]*>.*?</table>)',
    html,
    flags=re.I | re.S,
)
if not m:
    print("no tracklist table")
else:
    t = m.group(1)
    # simplify
    t = re.sub(r"\s+", " ", t)
    print(t[:2500])
