"""Wikidata search + SPARQL for composer discographies (songs only)."""

from __future__ import annotations

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
        "User-Agent": "SongsLibrary/0.1 (https://github.com/meistersolutions; NoRepeat companion)",
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


COMPOSER_WORKS_SPARQL = """
SELECT DISTINCT ?work ?workLabel ?year ?filmLabel ?performerLabel ?lyricistLabel WHERE {{
  ?work wdt:P86 wd:{qid} .
  ?work wdt:P31/wdt:P279* wd:Q7366 .
  FILTER NOT EXISTS {{ ?work wdt:P31/wdt:P279* wd:Q11424 }}
  FILTER NOT EXISTS {{ ?work wdt:P31/wdt:P279* wd:Q24856 }}
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

COMPOSER_FILM_SONGS_SPARQL = """
SELECT DISTINCT ?work ?workLabel ?year ?filmLabel ?performerLabel ?lyricistLabel WHERE {{
  ?film wdt:P86 wd:{qid} .
  ?film wdt:P31/wdt:P279* wd:Q11424 .
  ?work wdt:P361 ?film .
  ?work wdt:P31/wdt:P279* wd:Q7366 .
  OPTIONAL {{ ?work wdt:P577 ?date . BIND(YEAR(?date) AS ?year) }}
  OPTIONAL {{ ?film wdt:P577 ?fdate . BIND(YEAR(?fdate) AS ?year) }}
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


async def _run_sparql(query: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=120.0, headers=_headers()) as client:
        resp = await client.get(
            settings.wikidata_sparql_url,
            params={"format": "json", "query": query},
        )
        resp.raise_for_status()
        payload = resp.json()
    return payload.get("results", {}).get("bindings", [])


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
    half = max(limit // 2, 50)
    direct = await _run_sparql(COMPOSER_WORKS_SPARQL.format(qid=qid, limit=half))
    via_film = await _run_sparql(COMPOSER_FILM_SONGS_SPARQL.format(qid=qid, limit=limit))
    merged = {w["wikidata_id"]: w for w in _rows_to_works(direct)}
    for w in _rows_to_works(via_film):
        merged[w["wikidata_id"]] = w
    return list(merged.values())[:limit]
