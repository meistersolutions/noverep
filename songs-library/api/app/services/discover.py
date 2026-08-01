from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Song
from app.schemas import DiscoverSeedResult, SongCreate
from app.services.hashing import content_hash
from app.services import wiki_crawl, wikidata


def upsert_song(
    db: Session, data: SongCreate, *, composer_fallback: str | None = None
) -> tuple[Song, str]:
    """Insert or enrich an existing song.

    Returns (song, action) where action is inserted|skipped|updated.
    """
    composer = data.composer_name or composer_fallback
    h = content_hash(
        data.song_name,
        data.movie_name,
        release_year=data.release_year,
        language=data.language,
    )

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
        if composer and not existing.composer_name:
            existing.composer_name = composer
            changed = True
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


def _work_key(work: dict) -> tuple[str, str, str, str]:
    return (
        (work.get("song_name") or "").strip().casefold(),
        (work.get("movie_name") or "").strip().casefold(),
        str(work.get("release_year") or ""),
        (work.get("language") or "").strip().casefold(),
    )


async def resolve_seed_meta(seed: str) -> tuple[str | None, str | None]:
    return await wikidata.resolve_entity(seed)


def merge_and_upsert_works(
    db: Session,
    *,
    works: list[dict],
    seed: str,
    entity_qid: str | None = None,
    composer_name: str | None = None,
) -> dict[str, int]:
    """Upsert discovered works. Composer comes from each work when present.

    ``composer_name`` is only a soft fallback for sources that omit the field
    (legacy MusicBrainz/Wikidata paths) — never used to override page credits.
    """
    merged: dict[tuple[str, str], dict] = {}
    for work in works:
        name = (work.get("song_name") or "").strip()
        if not name or name == work.get("wikidata_id"):
            continue
        # Drop rows that are clearly the person name, not a song title.
        seed_cf = seed.strip().casefold()
        if seed_cf and name.casefold() == seed_cf:
            continue
        if composer_name and name.casefold() == composer_name.casefold():
            continue
        key = _work_key(work)
        existing = merged.get(key)
        if not existing:
            merged[key] = dict(work)
            continue
        for field in (
            "movie_name",
            "release_year",
            "wikidata_id",
            "musicbrainz_id",
            "wikipedia_title",
            "language",
            "composer_name",
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
            composer_name=work.get("composer_name") or None,
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
        # Soft fallback only when the page/table had no composer credit.
        fallback = None if create.composer_name else composer_name
        _, action = upsert_song(db, create, composer_fallback=fallback)
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
    """Run classified Wikipedia BFS for one seed (sync/debug path)."""
    result = DiscoverSeedResult(seed=seed)
    try:
        qid, label = await resolve_seed_meta(seed)
        result.entity_id = qid
        result.entity_label = label

        max_pages = None
        if limit is not None and limit > 0:
            max_pages = limit
        elif settings.discover_limit_per_seed > 0:
            max_pages = settings.discover_limit_per_seed

        crawl = await wiki_crawl.crawl_seed_bfs(seed, max_pages=max_pages)
        works = crawl["works"]
        if not works and not crawl.get("pages_done"):
            result.error = "Could not resolve seed to Wikipedia pages"
            return result

        stats = merge_and_upsert_works(
            db,
            works=works,
            seed=seed,
            entity_qid=qid,
            composer_name=None,
        )
        result.found = stats["found"]
        result.inserted = stats["inserted"]
        result.skipped = stats["skipped"]
        result.updated = stats["updated"]
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
