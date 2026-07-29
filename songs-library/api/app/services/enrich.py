"""Fill missing singers / lyricists from Wikidata."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Song
from app.services import wikidata


def _headers() -> dict[str, str]:
    return {
        "User-Agent": settings.user_agent,
        "Accept": "application/json",
    }


def _sparql_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


async def lookup_credits(
    song_name: str,
    *,
    composer_qid: str | None = None,
    movie_name: str | None = None,
) -> dict[str, Any]:
    """Resolve performers / lyricists for a song via Wikidata."""
    label = _sparql_escape(song_name.strip())
    if not label:
        return {"singers": [], "lyricists": [], "wikidata_id": None}

    composer_filter = f"?work wdt:P86 wd:{composer_qid} ." if composer_qid else ""
    movie_optional = ""
    if movie_name:
        movie_optional = f"""
          OPTIONAL {{
            ?work wdt:P361 ?film .
            ?film rdfs:label "{_sparql_escape(movie_name)}"@en .
          }}
        """

    query = f"""
    SELECT DISTINCT ?work ?workLabel ?performerLabel ?lyricistLabel WHERE {{
      ?work rdfs:label "{label}"@en .
      {composer_filter}
      OPTIONAL {{ ?work wdt:P175 ?performer . }}
      OPTIONAL {{ ?work wdt:P676 ?lyricist . }}
      {movie_optional}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,ta,hi,ml,te". }}
    }}
    LIMIT 40
    """

    async with httpx.AsyncClient(timeout=60.0, headers=_headers()) as client:
        for attempt in range(3):
            resp = await client.get(
                settings.wikidata_sparql_url,
                params={"format": "json", "query": query},
            )
            if resp.status_code == 429:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                # Fallback: search entity by name then fetch claims loosely
                break
            resp.raise_for_status()
            bindings = resp.json().get("results", {}).get("bindings", [])
            return _bindings_to_credits(bindings)

    return await _search_entity_credits(song_name, composer_qid=composer_qid)


def _bindings_to_credits(bindings: list[dict[str, Any]]) -> dict[str, Any]:
    singers: list[str] = []
    lyricists: list[str] = []
    wid = None
    for row in bindings:
        uri = (row.get("work") or {}).get("value") or ""
        if "/entity/" in uri and not wid:
            wid = uri.rsplit("/", 1)[-1]
        performer = (row.get("performerLabel") or {}).get("value")
        lyricist = (row.get("lyricistLabel") or {}).get("value")
        if performer and not performer.startswith("http") and performer not in singers:
            singers.append(performer)
        if lyricist and not lyricist.startswith("http") and lyricist not in lyricists:
            lyricists.append(lyricist)
    return {"singers": singers, "lyricists": lyricists, "wikidata_id": wid}


async def _search_entity_credits(
    song_name: str, *, composer_qid: str | None
) -> dict[str, Any]:
    params = {
        "action": "wbsearchentities",
        "search": song_name,
        "language": "en",
        "type": "item",
        "limit": 5,
        "format": "json",
    }
    async with httpx.AsyncClient(timeout=40.0, headers=_headers()) as client:
        resp = await client.get(settings.wikidata_api_url, params=params)
        if resp.status_code != 200:
            return {"singers": [], "lyricists": [], "wikidata_id": None}
        hits = resp.json().get("search") or []
        if not hits:
            return {"singers": [], "lyricists": [], "wikidata_id": None}
        qid = hits[0].get("id")
        if not qid:
            return {"singers": [], "lyricists": [], "wikidata_id": None}

        # Pull claims via SPARQL for this QID
        composer_line = (
            f"FILTER EXISTS {{ wd:{qid} wdt:P86 wd:{composer_qid} }} ."
            if composer_qid
            else ""
        )
        query = f"""
        SELECT ?performerLabel ?lyricistLabel WHERE {{
          BIND(wd:{qid} AS ?work)
          {composer_line}
          OPTIONAL {{ ?work wdt:P175 ?performer . }}
          OPTIONAL {{ ?work wdt:P676 ?lyricist . }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,ta". }}
        }}
        LIMIT 30
        """
        sparql = await client.get(
            settings.wikidata_sparql_url,
            params={"format": "json", "query": query},
        )
        if sparql.status_code != 200:
            return {"singers": [], "lyricists": [], "wikidata_id": qid}
        credits = _bindings_to_credits(sparql.json().get("results", {}).get("bindings", []))
        credits["wikidata_id"] = credits.get("wikidata_id") or qid
        return credits


async def lookup_film_metadata(movie_name: str) -> dict[str, Any]:
    """Directors and cast from Wikidata for a film title."""
    label = _sparql_escape(movie_name.strip())
    if not label:
        return {"directors": [], "actors": [], "actresses": []}

    query = f"""
    SELECT DISTINCT ?directorLabel ?castLabel ?genderLabel WHERE {{
      ?film rdfs:label "{label}"@en .
      ?film wdt:P31/wdt:P279* wd:Q11424 .
      OPTIONAL {{ ?film wdt:P57 ?director . }}
      OPTIONAL {{
        ?film wdt:P161 ?cast .
        OPTIONAL {{ ?cast wdt:P21 ?gender . }}
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,ta,hi,ml,te". }}
    }}
    LIMIT 80
    """
    async with httpx.AsyncClient(timeout=60.0, headers=_headers()) as client:
        for attempt in range(3):
            resp = await client.get(
                settings.wikidata_sparql_url,
                params={"format": "json", "query": query},
            )
            if resp.status_code == 429:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code != 200:
                break
            bindings = resp.json().get("results", {}).get("bindings", [])
            directors: list[str] = []
            actors: list[str] = []
            actresses: list[str] = []
            for row in bindings:
                d = (row.get("directorLabel") or {}).get("value")
                if d and not d.startswith("http") and d not in directors:
                    directors.append(d)
                cast = (row.get("castLabel") or {}).get("value")
                gender = (row.get("genderLabel") or {}).get("value") or ""
                if not cast or cast.startswith("http"):
                    continue
                g = gender.casefold()
                if "female" in g or g.endswith("1072"):
                    if cast not in actresses:
                        actresses.append(cast)
                elif "male" in g or g.endswith("1097"):
                    if cast not in actors:
                        actors.append(cast)
                elif cast not in actors:
                    actors.append(cast)
            return {"directors": directors, "actors": actors, "actresses": actresses}
    return {"directors": [], "actors": [], "actresses": []}


async def enrich_song(db: Session, song: Song, *, composer_qid: str | None) -> bool:
    credits = await lookup_credits(
        song.song_name,
        composer_qid=composer_qid,
        movie_name=song.movie_name,
    )
    changed = False
    if credits.get("singers") and not (song.singers or []):
        song.singers = list(credits["singers"])
        changed = True
    if credits.get("lyricists") and not (song.lyricists or []):
        song.lyricists = list(credits["lyricists"])
        changed = True
    if credits.get("wikidata_id") and not song.wikidata_id:
        clash = (
            db.query(Song)
            .filter(Song.wikidata_id == credits["wikidata_id"], Song.id != song.id)
            .one_or_none()
        )
        if not clash:
            song.wikidata_id = credits["wikidata_id"]
            changed = True

    if song.movie_name and (
        not (song.directors or [])
        or not (song.actors or [])
        or not (song.actresses or [])
    ):
        film_meta = await lookup_film_metadata(song.movie_name)
        if film_meta.get("directors") and not (song.directors or []):
            song.directors = list(film_meta["directors"])
            changed = True
        if film_meta.get("actors") and not (song.actors or []):
            song.actors = list(film_meta["actors"])
            changed = True
        if film_meta.get("actresses") and not (song.actresses or []):
            song.actresses = list(film_meta["actresses"])
            changed = True

    extra = dict(song.extra or {})
    extra["enrich_attempts"] = int(extra.get("enrich_attempts") or 0) + 1
    if changed:
        extra["enriched_via"] = "wikidata"
    song.extra = extra
    return changed


def songs_needing_enrichment(db: Session, *, limit: int = 25) -> list[Song]:
    rows = (
        db.query(Song)
        .order_by(Song.updated_at.asc(), Song.created_at.asc())
        .limit(limit * 6)
        .all()
    )
    need: list[Song] = []
    for song in rows:
        missing_credits = not (song.singers or []) or not (song.lyricists or [])
        missing_film = song.movie_name and (
            not (song.directors or []) or not (song.actors or []) or not (song.actresses or [])
        )
        if not missing_credits and not missing_film:
            continue
        extra = song.extra or {}
        if extra.get("enrich_attempts", 0) >= 3:
            continue
        need.append(song)
        if len(need) >= limit:
            break
    return need


async def enrich_batch(db: Session, *, limit: int = 20) -> dict[str, int]:
    songs = songs_needing_enrichment(db, limit=limit)
    updated = 0
    checked = 0
    qid_cache: dict[str, str | None] = {}

    for song in songs:
        checked += 1
        composer = (song.composer_name or "").strip()
        if composer not in qid_cache:
            try:
                qid, _ = await wikidata.resolve_entity(composer or song.seed_query or "")
            except Exception:  # noqa: BLE001
                qid = None
            qid_cache[composer] = qid
        try:
            if await enrich_song(db, song, composer_qid=qid_cache[composer]):
                updated += 1
        except Exception:  # noqa: BLE001
            extra = dict(song.extra or {})
            extra["enrich_attempts"] = int(extra.get("enrich_attempts") or 0) + 1
            song.extra = extra
        await asyncio.sleep(0.35)

    db.commit()
    return {"checked": checked, "updated": updated}
