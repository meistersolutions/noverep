from __future__ import annotations

import asyncio

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Song
from app.schemas import DiscoverSeedResult, SongCreate
from app.services.hashing import content_hash
from app.services import wikidata, wikipedia


def upsert_song(db: Session, data: SongCreate, *, composer_fallback: str | None = None) -> tuple[Song, bool]:
    composer = data.composer_name or composer_fallback
    h = content_hash(data.song_name, data.movie_name, composer, data.release_year)

    existing = None
    if data.wikidata_id:
        existing = db.query(Song).filter(Song.wikidata_id == data.wikidata_id).one_or_none()
    if not existing:
        existing = db.query(Song).filter(Song.content_hash == h).one_or_none()
    if existing:
        return existing, False

    song = Song(
        song_name=data.song_name.strip(),
        movie_name=(data.movie_name or None),
        release_year=data.release_year,
        composer_name=composer,
        singers=list(data.singers or []),
        lyricists=list(data.lyricists or []),
        popularity=float(data.popularity or 50.0),
        moods=list(data.moods or []),
        content_hash=h,
        wikidata_id=data.wikidata_id,
        musicbrainz_id=data.musicbrainz_id,
        youtube_video_id=data.youtube_video_id,
        wikipedia_title=data.wikipedia_title,
        playability="mapped" if data.youtube_video_id else "metadata_only",
        discovered_via=data.discovered_via,
        seed_query=data.seed_query,
        extra=data.extra,
    )
    db.add(song)
    db.flush()
    return song, True


def _work_key(work: dict) -> tuple[str, str]:
    return (
        (work.get("song_name") or "").strip().casefold(),
        (work.get("movie_name") or "").strip().casefold(),
    )


async def discover_seed(db: Session, seed: str, limit: int | None = None) -> DiscoverSeedResult:
    limit = limit or settings.discover_limit_per_seed
    result = DiscoverSeedResult(seed=seed)
    try:
        qid, label = await wikidata.resolve_entity(seed)
        result.entity_id = qid
        result.entity_label = label
        composer_name = label or seed.strip()

        async def _wd() -> list[dict]:
            if not qid:
                return []
            rows = await wikidata.fetch_composer_works(qid, limit=limit)
            for w in rows:
                w.setdefault("source", "wikidata_sparql")
            return rows

        async def _wiki() -> list[dict]:
            rows = await wikipedia.fetch_composer_songs(composer_name, limit=limit)
            for w in rows:
                w.setdefault("source", "wikipedia")
            return rows

        wd_result, wiki_result = await asyncio.gather(_wd(), _wiki(), return_exceptions=True)
        works: list[dict] = []
        errors: list[str] = []
        if isinstance(wd_result, Exception):
            errors.append(f"wikidata: {wd_result}")
        else:
            works.extend(wd_result)
        if isinstance(wiki_result, Exception):
            errors.append(f"wikipedia: {wiki_result}")
        else:
            works.extend(wiki_result)

        if not qid and not works:
            result.error = "Could not resolve seed to a Wikidata entity or Wikipedia song list"
            return result

        merged: dict[tuple[str, str], dict] = {}
        for work in works:
            name = (work.get("song_name") or "").strip()
            if not name or name == work.get("wikidata_id"):
                continue
            if name.casefold() == composer_name.casefold():
                continue
            key = _work_key(work)
            existing = merged.get(key)
            if not existing:
                merged[key] = work
                continue
            for field in ("movie_name", "release_year", "wikidata_id", "wikipedia_title"):
                if not existing.get(field) and work.get(field):
                    existing[field] = work[field]
            for field in ("singers", "lyricists"):
                for item in work.get(field) or []:
                    if item not in existing.setdefault(field, []):
                        existing[field].append(item)
            sources = {existing.get("source"), work.get("source")}
            if "wikidata_sparql" in sources and "wikipedia" in sources:
                existing["source"] = "wikidata+wikipedia"
            elif work.get("source") == "wikidata_sparql":
                existing["source"] = "wikidata_sparql"

        result.found = len(merged)

        for work in list(merged.values())[:limit]:
            create = SongCreate(
                song_name=work["song_name"].strip(),
                movie_name=work.get("movie_name"),
                release_year=work.get("release_year"),
                composer_name=composer_name,
                singers=work.get("singers") or [],
                lyricists=work.get("lyricists") or [],
                popularity=55.0,
                wikidata_id=work.get("wikidata_id"),
                wikipedia_title=work.get("wikipedia_title"),
                discovered_via=work.get("source") or "discovery",
                seed_query=seed,
                extra={"source_entity": qid} if qid else None,
            )
            _, inserted = upsert_song(db, create, composer_fallback=composer_name)
            if inserted:
                result.inserted += 1
            else:
                result.skipped += 1

        db.commit()
        if errors and result.found == 0:
            result.error = "; ".join(errors)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        result.error = str(exc)
    return result


async def discover_many(
    db: Session, seeds: list[str], limit_per_seed: int | None = None
) -> list[DiscoverSeedResult]:
    out: list[DiscoverSeedResult] = []
    for seed in seeds:
        cleaned = seed.strip()
        if not cleaned:
            continue
        out.append(await discover_seed(db, cleaned, limit=limit_per_seed))
    return out
