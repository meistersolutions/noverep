from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Song
from app.schemas import (
    DiscoverRequest,
    DiscoverResponse,
    ResolveYoutubeRequest,
    ResolveYoutubeResult,
    SampleRequest,
    SongCreate,
    SongOut,
    SongUpdate,
    StatsOut,
)
from app.services.discover import discover_many, upsert_song
from app.services.hashing import content_hash
from app.services.youtube_resolve import resolve_unmapped

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db)):
    total = db.query(func.count(Song.id)).scalar() or 0
    mapped = db.query(func.count(Song.id)).filter(Song.playability == "mapped").scalar() or 0
    meta = db.query(func.count(Song.id)).filter(Song.playability == "metadata_only").scalar() or 0
    rows = (
        db.query(Song.composer_name, func.count(Song.id))
        .group_by(Song.composer_name)
        .order_by(func.count(Song.id).desc())
        .all()
    )
    by_composer = {(name or "Unknown"): count for name, count in rows}
    return StatsOut(total_songs=total, by_composer=by_composer, mapped=mapped, metadata_only=meta)


@router.get("/songs", response_model=list[SongOut])
def list_songs(
    q: str | None = None,
    composer: str | None = None,
    movie: str | None = None,
    mood: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Song)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Song.song_name.ilike(like),
                Song.movie_name.ilike(like),
                Song.composer_name.ilike(like),
            )
        )
    if composer:
        query = query.filter(Song.composer_name.ilike(f"%{composer}%"))
    if movie:
        query = query.filter(Song.movie_name.ilike(f"%{movie}%"))
    # Keep unknown years (same behavior as NoRepeat discovery year filter).
    if year_from is not None and year_to is not None:
        query = query.filter(
            or_(
                Song.release_year.is_(None),
                Song.release_year.between(year_from, year_to),
            )
        )
    elif year_from is not None:
        query = query.filter(
            or_(Song.release_year.is_(None), Song.release_year >= year_from)
        )
    elif year_to is not None:
        query = query.filter(
            or_(Song.release_year.is_(None), Song.release_year <= year_to)
        )
    if mood:
        query = query.filter(Song.moods.contains([mood]))
    return (
        query.order_by(Song.composer_name, Song.release_year.desc(), Song.song_name)
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/songs/{song_id}", response_model=SongOut)
def get_song(song_id: str, db: Session = Depends(get_db)):
    song = db.query(Song).filter(Song.id == song_id).one_or_none()
    if not song:
        raise HTTPException(404, "Song not found")
    return song


@router.post("/songs", response_model=SongOut)
def create_song(body: SongCreate, db: Session = Depends(get_db)):
    song, inserted = upsert_song(db, body)
    if not inserted:
        raise HTTPException(409, "Song already exists")
    db.commit()
    db.refresh(song)
    return song


@router.patch("/songs/{song_id}", response_model=SongOut)
def update_song(song_id: str, body: SongUpdate, db: Session = Depends(get_db)):
    song = db.query(Song).filter(Song.id == song_id).one_or_none()
    if not song:
        raise HTTPException(404, "Song not found")
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(song, key, value)
    if any(k in data for k in ("song_name", "movie_name", "composer_name", "release_year")):
        song.content_hash = content_hash(
            song.song_name, song.movie_name, song.composer_name, song.release_year
        )
    if song.youtube_video_id and song.playability == "metadata_only":
        song.playability = "mapped"
    db.commit()
    db.refresh(song)
    return song


@router.post("/discover", response_model=DiscoverResponse)
async def discover(body: DiscoverRequest, db: Session = Depends(get_db)):
    results = await discover_many(db, body.seeds, limit_per_seed=body.limit_per_seed)
    return DiscoverResponse(
        results=results,
        total_inserted=sum(r.inserted for r in results),
        total_skipped=sum(r.skipped for r in results),
    )


@router.post("/sample", response_model=list[SongOut])
def sample(body: SampleRequest, db: Session = Depends(get_db)):
    query = db.query(Song)
    composer = body.composer or body.seed
    if composer:
        query = query.filter(Song.composer_name.ilike(f"%{composer}%"))
    if body.year_from is not None and body.year_to is not None:
        query = query.filter(
            or_(
                Song.release_year.is_(None),
                Song.release_year.between(body.year_from, body.year_to),
            )
        )
    elif body.year_from is not None:
        query = query.filter(
            or_(Song.release_year.is_(None), Song.release_year >= body.year_from)
        )
    elif body.year_to is not None:
        query = query.filter(
            or_(Song.release_year.is_(None), Song.release_year <= body.year_to)
        )
    if body.only_mapped:
        query = query.filter(Song.playability == "mapped")
    if body.exclude_hashes:
        query = query.filter(~Song.content_hash.in_(body.exclude_hashes))
    if body.exclude_ids:
        query = query.filter(~Song.id.in_(body.exclude_ids))
    if body.moods:
        for mood in body.moods:
            query = query.filter(Song.moods.contains([mood]))
    rows = (
        query.order_by(Song.popularity.desc(), Song.release_year.desc(), Song.song_name)
        .limit(body.limit)
        .all()
    )
    return rows


@router.post("/resolve/youtube", response_model=ResolveYoutubeResult)
async def resolve_youtube(body: ResolveYoutubeRequest, db: Session = Depends(get_db)):
    return await resolve_unmapped(
        db, limit=body.limit, composer=body.composer, dry_run=body.dry_run
    )
