"""Wikidata search + SPARQL for composer discographies."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.config import settings

KNOWN_COMPOSERS: dict[str, dict[str, str]] = {
    "ilaiyaraja": {"id": "Q2720141", "label": "Ilaiyaraaja"},
    "ilayaraja": {"id": "Q2720141", "label": "Ilaiyaraaja"},
    "ilayaraaja": {"id": "Q2720141", "label": "Ilaiyaraaja"},
    "a. r. rahman": {"id": "Q108560", "label": "A. R. Rahman"},
    "ar rahman": {"id": "Q108560", "label": "A. R. Rahman"},
    "a r rahman": {"id": "Q108560", "label": "A. R. Rahman"},
    "arr": {"id": "Q108560", "label": "A. R. Rahman"},
    "yuvan shankar raja": {"id": "Q1387724", "label": "Yuvan Shankar Raja"},
    "yuvan": {"id": "Q1387724", "label": "Yuvan Shankar Raja"},
    "ysr": {"id": "Q1387724", "label": "Yuvan Shankar Raja"},
}


def _headers() -> dict[str, str]:
    return {
        "User-Agent": settings.user_agent,
        "Accept": "application/json",
    }


def _normalize_seed_key(seed: str) -> str:
    return " ".join(seed.strip().casefold().replace(".", " ").split())


async def resolve_entity(seed: str) -> tuple[str | None, str | None]:
    key = _normalize_seed_key(seed)
    known = KNOWN_COMPOSERS.get(key) or KNOWN_COMPOSERS.get(seed.strip().casefold())
    if known:
        return known["id"], known["label"]

    params = {
        "action": "wbsearchentities",
        "search": seed,
        "language": "en",
        "type": "item",
        "limit": 8,
        "format": "json",
    }
    async with httpx.AsyncClient(timeout=40.0, headers=_headers()) as client:
        resp = await client.get(settings.wikidata_api_url, params=params)
        resp.raise_for_status()
        data = resp.json()

    for hit in data.get("search") or []:
        desc = (hit.get("description") or "").lower()
        label = hit.get("label") or seed
        if any(
            token in desc
            for token in ("composer", "musician", "music director", "singer", "film score")
        ):
            return hit.get("id"), label
    if data.get("search"):
        hit = data["search"][0]
        return hit.get("id"), hit.get("label")
    return None, None


# Tamil/Indian film composers rarely have P31=song (Q7366). Prefer musical works /
# anything composed by them that is not a film/TV series.
COMPOSER_MUSICAL_WORKS_SPARQL = """
SELECT DISTINCT ?work ?workLabel ?year ?filmLabel ?performerLabel ?lyricistLabel WHERE {{
  ?work wdt:P86 wd:{qid} .
  FILTER NOT EXISTS {{ ?work wdt:P31/wdt:P279* wd:Q11424 }}
  FILTER NOT EXISTS {{ ?work wdt:P31/wdt:P279* wd:Q24856 }}
  FILTER NOT EXISTS {{ ?work wdt:P31/wdt:P279* wd:Q15416 }}
  OPTIONAL {{ ?work wdt:P577 ?date . BIND(YEAR(?date) AS ?year) }}
  OPTIONAL {{
    ?work wdt:P361 ?film .
    ?film wdt:P31/wdt:P279* wd:Q11424 .
  }}
  OPTIONAL {{ ?work wdt:P175 ?performer . }}
  OPTIONAL {{ ?work wdt:P676 ?lyricist . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,ta,hi,ml,te". }}
}}
LIMIT {limit}
"""

COMPOSER_MUSICAL_CLASS_SPARQL = """
SELECT DISTINCT ?work ?workLabel ?year ?filmLabel ?performerLabel ?lyricistLabel WHERE {{
  ?work wdt:P86 wd:{qid} .
  ?work wdt:P31/wdt:P279* wd:Q2188189 .
  OPTIONAL {{ ?work wdt:P577 ?date . BIND(YEAR(?date) AS ?year) }}
  OPTIONAL {{
    ?work wdt:P361 ?film .
    ?film wdt:P31/wdt:P279* wd:Q11424 .
  }}
  OPTIONAL {{ ?work wdt:P175 ?performer . }}
  OPTIONAL {{ ?work wdt:P676 ?lyricist . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,ta,hi,ml,te". }}
}}
LIMIT {limit}
"""


def _literal(row: dict[str, Any], key: str) -> str | None:
    node = row.get(key)
    if not node:
        return None
    value = node.get("value")
    if not value or value.startswith("http://www.wikidata.org/entity/"):
        return None
    return value


def _qid_from_uri(uri: str | None) -> str | None:
    if not uri:
        return None
    if "/entity/" in uri:
        return uri.rsplit("/", 1)[-1]
    return None


async def _run_sparql(query: str, *, attempts: int = 4) -> list[dict[str, Any]]:
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=120.0, headers=_headers()) as client:
        for attempt in range(attempts):
            try:
                resp = await client.get(
                    settings.wikidata_sparql_url,
                    params={"format": "json", "query": query},
                )
                if resp.status_code == 429:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                resp.raise_for_status()
                payload = resp.json()
                return payload.get("results", {}).get("bindings", [])
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                await asyncio.sleep(1.0 * (attempt + 1))
    if last_exc:
        raise last_exc
    return []


def _rows_to_works(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_work: dict[str, dict[str, Any]] = {}
    for row in bindings:
        work_uri = (row.get("work") or {}).get("value")
        wid = _qid_from_uri(work_uri)
        if not wid:
            continue
        entry = by_work.setdefault(
            wid,
            {
                "wikidata_id": wid,
                "song_name": _literal(row, "workLabel") or wid,
                "movie_name": None,
                "release_year": None,
                "singers": [],
                "lyricists": [],
                "source": "wikidata_sparql",
            },
        )
        film = _literal(row, "filmLabel")
        if film and not entry["movie_name"]:
            entry["movie_name"] = film
        year_raw = _literal(row, "year")
        if year_raw and not entry["release_year"]:
            try:
                entry["release_year"] = int(float(year_raw))
            except ValueError:
                pass
        performer = _literal(row, "performerLabel")
        if performer and performer not in entry["singers"]:
            entry["singers"].append(performer)
        lyricist = _literal(row, "lyricistLabel")
        if lyricist and lyricist not in entry["lyricists"]:
            entry["lyricists"].append(lyricist)
    return list(by_work.values())


async def fetch_composer_works(qid: str, limit: int) -> list[dict[str, Any]]:
    """Return musical works composed by qid (excludes films themselves)."""
    half = max(limit, 50)
    musical = await _run_sparql(
        COMPOSER_MUSICAL_CLASS_SPARQL.format(qid=qid, limit=half)
    )
    loose = await _run_sparql(
        COMPOSER_MUSICAL_WORKS_SPARQL.format(qid=qid, limit=half)
    )
    merged = {w["wikidata_id"]: w for w in _rows_to_works(musical)}
    for w in _rows_to_works(loose):
        existing = merged.get(w["wikidata_id"])
        if not existing:
            merged[w["wikidata_id"]] = w
            continue
        if not existing.get("movie_name") and w.get("movie_name"):
            existing["movie_name"] = w["movie_name"]
        if not existing.get("release_year") and w.get("release_year"):
            existing["release_year"] = w["release_year"]
        for singer in w.get("singers") or []:
            if singer not in existing["singers"]:
                existing["singers"].append(singer)
        for lyricist in w.get("lyricists") or []:
            if lyricist not in existing["lyricists"]:
                existing["lyricists"].append(lyricist)
    return list(merged.values())[:limit]
