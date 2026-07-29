from __future__ import annotations

import asyncio

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Song
from app.schemas import DiscoverSeedResult, SongCreate
from app.services.hashing import content_hash
from app.services import musicbrainz, wikidata, wikipedia


def upsert_song(
    db: Session, data: SongCreate, *, composer_fallback: str | None = None
) -> tuple[Song, str]:
    """Insert or enrich an existing song.

    Returns (song, action) where action is inserted|skipped|updated.
    """
    composer = data.composer_name or composer_fallback
    h = content_hash(data.song_name, data.movie_name, composer, data.release_year)

    existing = None
    if data.wikidata_id:
        existing = db.query(Song).filter(Song.wikidata_id == data.wikidata_id).one_or_none()
    if not existing and data.musicbrainz_id:
        existing = (
            db.query(Song).filter(Song.musicbrainz_id == data.musicbrainz_id).one_or_none()
        )
    if not existing:
        existing = db.query(Song).filter(Song.content_hash == h).one_or_none()

    if existing:
        changed = False
        if data.singers and not (existing.singers or []):
            existing.singers = list(data.singers)
            changed = True
        if data.lyricists and not (existing.lyricists or []):
            existing.lyricists = list(data.lyricists)
            changed = True
        if data.movie_name and not existing.movie_name:
            existing.movie_name = data.movie_name
            changed = True
        if data.release_year and not existing.release_year:
            existing.release_year = data.release_year
            changed = True
        if data.wikidata_id and not existing.wikidata_id:
            existing.wikidata_id = data.wikidata_id
            changed = True
        if data.musicbrainz_id and not existing.musicbrainz_id:
            existing.musicbrainz_id = data.musicbrainz_id
            changed = True
        if data.wikipedia_title and not existing.wikipedia_title:
            existing.wikipedia_title = data.wikipedia_title
            changed = True
        if data.language and not existing.language:
            existing.language = data.language
            changed = True
        for field in ("directors", "actors", "actresses"):
            vals = getattr(data, field) or []
            existing_vals = getattr(existing, field) or []
            if vals and not existing_vals:
                setattr(existing, field, list(vals))
                changed = True
        return existing, "updated" if changed else "skipped"

    song = Song(
        song_name=data.song_name.strip(),
        movie_name=(data.movie_name or None),
        release_year=data.release_year,
        composer_name=composer,
        singers=list(data.singers or []),
        lyricists=list(data.lyricists or []),
        language=data.language,
        directors=list(data.directors or []),
        actors=list(data.actors or []),
        actresses=list(data.actresses or []),
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
    return song, "inserted"


def _work_key(work: dict) -> tuple[str, str]:
    return (
        (work.get("song_name") or "").strip().casefold(),
        (work.get("movie_name") or "").strip().casefold(),
    )


async def resolve_seed_meta(seed: str) -> tuple[str | None, str | None]:
    return await wikidata.resolve_entity(seed)


def merge_and_upsert_works(
    db: Session,
    *,
    works: list[dict],
    composer_name: str,
    seed: str,
    entity_qid: str | None,
) -> dict[str, int]:
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
            for field in (
                "movie_name",
                "release_year",
                "wikidata_id",
                "musicbrainz_id",
                "wikipedia_title",
                "language",
            ):
                if not existing.get(field) and work.get(field):
                    existing[field] = work[field]
            for field in ("singers", "lyricists", "directors", "actors", "actresses"):
            for item in work.get(field) or []:
                if item not in existing.setdefault(field, []):
                    existing[field].append(item)
        sources = {existing.get("source"), work.get("source")}
        if len([s for s in sources if s]) > 1:
            existing["source"] = "+".join(sorted(s for s in sources if s))

    inserted = skipped = updated = 0
    for work in merged.values():
            create = SongCreate(
                song_name=work["song_name"].strip(),
                movie_name=work.get("movie_name"),
                release_year=work.get("release_year"),
                composer_name=composer_name,
                singers=work.get("singers") or [],
                lyricists=work.get("lyricists") or [],
                language=work.get("language"),
                directors=work.get("directors") or [],
                actors=work.get("actors") or [],
                actresses=work.get("actresses") or [],
                popularity=55.0,
            wikidata_id=work.get("wikidata_id"),
            musicbrainz_id=work.get("musicbrainz_id"),
            wikipedia_title=work.get("wikipedia_title"),
            discovered_via=work.get("source") or "discovery",
            seed_query=seed,
            extra={"source_entity": entity_qid} if entity_qid else None,
        )
        _, action = upsert_song(db, create, composer_fallback=composer_name)
        if action == "inserted":
            inserted += 1
        elif action == "updated":
            updated += 1
        else:
            skipped += 1
    db.commit()
    return {
        "found": len(merged),
        "inserted": inserted,
        "skipped": skipped,
        "updated": updated,
    }


async def discover_seed(db: Session, seed: str, limit: int | None = None) -> DiscoverSeedResult:
    """Synchronous-style discover used by the API when not using background jobs.

    limit=None means ingest everything Wikipedia returns (plus Wikidata / MB caps).
    """
    if limit is None:
        limit = settings.discover_limit_per_seed
    # 0 or negative => unlimited wikipedia list ingest
    unlimited = limit <= 0
    wiki_limit = None if unlimited else limit

    result = DiscoverSeedResult(seed=seed)
    try:
        qid, label = await resolve_seed_meta(seed)
        result.entity_id = qid
        result.entity_label = label
        composer_name = label or seed.strip()

        async def _wd() -> list[dict]:
            if not qid:
                return []
            rows = await wikidata.fetch_composer_works(
                qid, limit=limit if not unlimited else settings.discover_wikidata_limit
            )
            for w in rows:
                w.setdefault("source", "wikidata_sparql")
            return rows

        async def _wiki() -> list[dict]:
            rows = await wikipedia.fetch_composer_songs(composer_name, limit=wiki_limit)
            for w in rows:
                w.setdefault("source", "wikipedia")
            return rows

        async def _mb() -> list[dict]:
            mb_id, _ = await musicbrainz.resolve_artist_id(composer_name)
            if not mb_id:
                return []
            rows = await musicbrainz.fetch_artist_works(
                mb_id,
                limit=settings.discover_musicbrainz_limit
                if unlimited
                else min(settings.discover_musicbrainz_limit, limit or 500),
            )
            return rows

        gathered = await asyncio.gather(_wd(), _wiki(), _mb(), return_exceptions=True)
        works: list[dict] = []
        errors: list[str] = []
        labels = ("wikidata", "wikipedia", "musicbrainz")
        for label_name, item in zip(labels, gathered):
            if isinstance(item, Exception):
                errors.append(f"{label_name}: {item}")
            else:
                works.extend(item)

        if not qid and not works:
            result.error = "Could not resolve seed to a Wikidata entity or Wikipedia song list"
            return result

        stats = merge_and_upsert_works(
            db,
            works=works,
            composer_name=composer_name,
            seed=seed,
            entity_qid=qid,
        )
        result.found = stats["found"]
        result.inserted = stats["inserted"]
        result.skipped = stats["skipped"]
        result.updated = stats["updated"]
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
