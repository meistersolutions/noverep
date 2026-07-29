from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Song
from app.schemas import DiscoverSeedResult, SongCreate
from app.services.hashing import content_hash
from app.services import wikidata


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


async def discover_seed(db: Session, seed: str, limit: int | None = None) -> DiscoverSeedResult:
    limit = limit or settings.discover_limit_per_seed
    result = DiscoverSeedResult(seed=seed)
    try:
        qid, label = await wikidata.resolve_entity(seed)
        result.entity_id = qid
        result.entity_label = label
        if not qid:
            result.error = "Could not resolve seed to a Wikidata entity"
            return result

        works = await wikidata.fetch_composer_works(qid, limit=limit)
        result.found = len(works)
        composer_name = label or seed

        for work in works:
            name = (work.get("song_name") or "").strip()
            if not name or name == work.get("wikidata_id"):
                continue
            if name.casefold() == (composer_name or "").casefold():
                continue

            create = SongCreate(
                song_name=name,
                movie_name=work.get("movie_name"),
                release_year=work.get("release_year"),
                composer_name=composer_name,
                singers=work.get("singers") or [],
                lyricists=work.get("lyricists") or [],
                popularity=55.0,
                wikidata_id=work.get("wikidata_id"),
                discovered_via="wikidata_sparql",
                seed_query=seed,
                extra={"source_entity": qid},
            )
            _, inserted = upsert_song(db, create, composer_fallback=composer_name)
            if inserted:
                result.inserted += 1
            else:
                result.skipped += 1

        db.commit()
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
