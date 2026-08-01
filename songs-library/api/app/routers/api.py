from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import DiscoverJob, Song
from app.schemas import (
    DiscoverJobOut,
    DiscoverRequest,
    DiscoverResponse,
    EnrichStatusOut,
    ComposerOut,
    PlaylistExportRequest,
    PlaylistExportResponse,
    ResolveYoutubeRequest,
    ResolveYoutubeResult,
    SampleRequest,
    SongCreate,
    SongOut,
    SongUpdate,
    StatsOut,
    WorkerStatusOut,
)
from app.services.discover import discover_many, upsert_song
from app.services.hashing import content_hash
from app.services.playlist_export import export_playlist
from app.services.youtube_resolve import (
    resolve_unmapped,
    resolve_one_song,
    refresh_popularity_from_views,
    _data_api_configured,
    get_resolve_status,
)

router = APIRouter(prefix="/api")

# Map preference codes → labels/aliases stored on Song.language from Wikipedia.
_LANGUAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "tamil": ("tamil", "tamizh", "ta", "தமிழ்"),
    "hindi": ("hindi", "bollywood", "hi", "हिंदी", "हिन्दी"),
    "telugu": ("telugu", "te", "తెలుగు"),
    "malayalam": ("malayalam", "ml", "മലയാളം"),
    "kannada": ("kannada", "kn", "ಕನ್ನಡ"),
    "english": ("english", "en"),
    "punjabi": ("punjabi", "pa", "ਪੰਜਾਬੀ"),
}


def _language_match_terms(languages: list[str]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for raw in languages:
        key = (raw or "").strip().casefold()
        if not key:
            continue
        aliases = _LANGUAGE_ALIASES.get(key, (key,))
        for alias in aliases:
            a = alias.casefold()
            if a not in seen:
                seen.add(a)
                terms.append(alias)
    return terms


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
    return StatsOut(
        total_songs=total,
        by_composer=by_composer,
        mapped=mapped,
        metadata_only=meta,
        youtube_api_configured=_data_api_configured(),
    )


@router.get("/composers", response_model=list[ComposerOut])
def list_composers(db: Session = Depends(get_db)):
    """Composer names with distinct movie/album and song counts."""
    movie_key = func.nullif(func.trim(Song.movie_name), "")
    rows = (
        db.query(
            Song.composer_name,
            func.count(Song.id),
            func.count(func.distinct(movie_key)),
        )
        .group_by(Song.composer_name)
        .order_by(func.count(Song.id).desc(), Song.composer_name)
        .all()
    )
    return [
        ComposerOut(
            name=name or "Unknown",
            song_count=int(song_count),
            movie_count=int(movie_count),
        )
        for name, song_count, movie_count in rows
    ]


@router.get("/songs", response_model=list[SongOut])
def list_songs(
    q: str | None = None,
    composer: str | None = None,
    movie: str | None = None,
    mood: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    limit: int = Query(default=50, ge=1, le=2000),
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


@router.post("/songs/{song_id}/resolve-youtube", response_model=SongOut)
async def resolve_song_youtube(song_id: str, db: Session = Depends(get_db)):
    song = db.query(Song).filter(Song.id == song_id).one_or_none()
    if not song:
        raise HTTPException(404, "Song not found")
    resolved = await resolve_one_song(db, song)
    if not resolved or not resolved.youtube_video_id:
        raise HTTPException(
            422,
            "Could not resolve YouTube video for this song",
        )
    return resolved


@router.post("/songs", response_model=SongOut)
def create_song(body: SongCreate, db: Session = Depends(get_db)):
    song, action = upsert_song(db, body)
    if action != "inserted":
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
    if any(k in data for k in ("song_name", "movie_name", "release_year", "language")):
        song.content_hash = content_hash(
            song.song_name,
            song.movie_name,
            release_year=song.release_year,
            language=song.language,
        )
    if song.youtube_video_id and song.playability == "metadata_only":
        song.playability = "mapped"
    db.commit()
    db.refresh(song)
    return song


@router.post("/discover", response_model=DiscoverResponse)
async def discover(body: DiscoverRequest, db: Session = Depends(get_db)):
    """Queue continuous discovery jobs (Wikipedia pages → films → MusicBrainz).

    Pass limit_per_seed=0 (default) for full ingest. A positive limit runs a
    one-shot capped discover for debugging.
    """
    limit = body.limit_per_seed
    if limit is not None and limit > 0:
        results = await discover_many(db, body.seeds, limit_per_seed=limit)
        return DiscoverResponse(
            results=results,
            total_inserted=sum(r.inserted for r in results),
            total_skipped=sum(r.skipped for r in results),
            total_updated=sum(r.updated for r in results),
            job_ids=[],
        )

    job_ids: list[str] = []
    for seed in body.seeds:
        cleaned = seed.strip()
        if not cleaned:
            continue
        # Reuse an already-running job for the same seed.
        active = (
            db.query(DiscoverJob)
            .filter(
                DiscoverJob.seed == cleaned,
                DiscoverJob.status.in_(("pending", "running")),
            )
            .order_by(DiscoverJob.created_at.desc())
            .first()
        )
        if active:
            job_ids.append(active.id)
            continue
        job = DiscoverJob(seed=cleaned, status="pending", phase="queued", message="Queued")
        db.add(job)
        db.flush()
        job_ids.append(job.id)
    db.commit()
    return DiscoverResponse(
        results=[],
        total_inserted=0,
        total_skipped=0,
        total_updated=0,
        job_ids=job_ids,
    )


@router.get("/discover/jobs/{job_id}", response_model=DiscoverJobOut)
def discover_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(DiscoverJob).filter(DiscoverJob.id == job_id).one_or_none()
    if not job:
        raise HTTPException(404, "Discover job not found")
    return job


@router.post("/discover/jobs/{job_id}/end", response_model=DiscoverJobOut)
def end_and_archive_discover_job(
    job_id: str, db: Session = Depends(get_db)
) -> DiscoverJob:
    """Stop a pending/running seed job and archive it off the home list."""
    job = db.query(DiscoverJob).filter(DiscoverJob.id == job_id).one_or_none()
    if not job:
        raise HTTPException(404, "Discover job not found")
    if job.status == "archived":
        return job
    now = datetime.now(timezone.utc)
    was_active = job.status in {"pending", "running"}
    job.status = "archived"
    job.phase = "stopped" if was_active else (job.phase or "done")
    job.message = (
        "Ended and archived by user"
        if was_active
        else (job.message or "Archived")
    )
    if was_active or job.finished_at is None:
        job.finished_at = now
    db.commit()
    db.refresh(job)
    return job


@router.post("/discover/jobs/{job_id}/restart", response_model=DiscoverJobOut)
def restart_discover_job(
    job_id: str,
    reset: bool = Query(
        default=False,
        description="If true, clear progress and start from scratch; else resume film crawl.",
    ),
    db: Session = Depends(get_db),
) -> DiscoverJob:
    """Re-queue a stuck/failed/completed seed so the background worker runs it again."""
    from app.services.worker import requeue_discover_job

    job = db.query(DiscoverJob).filter(DiscoverJob.id == job_id).one_or_none()
    if not job:
        raise HTTPException(404, "Discover job not found")
    if job.status == "archived":
        raise HTTPException(400, "Archived jobs cannot be restarted; discover the seed again")
    return requeue_discover_job(db, job, reset_progress=reset)


@router.get("/discover/jobs", response_model=list[DiscoverJobOut])
def list_discover_jobs(
    limit: int = Query(default=20, ge=1, le=50),
    active_only: bool = Query(default=False),
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """List discover jobs. Active (pending/running) are listed first.

    Archived jobs are hidden unless include_archived=true.
    """
    active = (
        db.query(DiscoverJob)
        .filter(DiscoverJob.status.in_(("pending", "running")))
        .order_by(DiscoverJob.created_at.desc())
        .all()
    )
    if active_only:
        return active[:limit]
    remaining = max(limit - len(active), 0)
    recent: list[DiscoverJob] = []
    if remaining:
        finished_q = db.query(DiscoverJob).filter(
            ~DiscoverJob.status.in_(("pending", "running"))
        )
        if not include_archived:
            finished_q = finished_q.filter(DiscoverJob.status != "archived")
        recent = (
            finished_q.order_by(DiscoverJob.created_at.desc()).limit(remaining).all()
        )
    return active + recent


@router.get("/enrich/status", response_model=EnrichStatusOut)
def enrich_status(db: Session = Depends(get_db)):
    songs = db.query(Song).all()
    missing_singers = sum(1 for s in songs if not (s.singers or []))
    missing_lyricists = sum(1 for s in songs if not (s.lyricists or []))
    missing_either = sum(
        1 for s in songs if not (s.singers or []) or not (s.lyricists or [])
    )
    return EnrichStatusOut(
        missing_singers=missing_singers,
        missing_lyricists=missing_lyricists,
        missing_either=missing_either,
    )


@router.get("/workers/status", response_model=WorkerStatusOut)
def workers_status(db: Session = Depends(get_db)):
    """Mapped backlog + last YouTube resolve batch (for the portal)."""
    total = db.query(func.count(Song.id)).scalar() or 0
    mapped = db.query(func.count(Song.id)).filter(Song.playability == "mapped").scalar() or 0
    meta = (
        db.query(func.count(Song.id)).filter(Song.playability == "metadata_only").scalar()
        or 0
    )
    resolve = get_resolve_status()
    last = resolve.get("last_batch") or {}
    pct = round(100.0 * mapped / total, 2) if total else 0.0
    hint = ""
    if not resolve.get("youtube_api_configured"):
        hint = "Set YOUTUBE_API_KEY on this Render service."
    elif last.get("attempted") and last.get("resolved") == 0 and last.get("failed", 0) > 0:
        hint = (
            "Last batch resolved 0 — check Render logs for youtube_data_api_* "
            "(quotaExceeded / empty search). Free API quota is ~100 searches/day."
        )
    elif meta > mapped * 10:
        hint = (
            "Unmapped backlog is large. Free YouTube Data API quota (~10k units/day, "
            "100 per search) limits mapping to roughly ~25–100 songs/day."
        )
    return WorkerStatusOut(
        total_songs=int(total),
        mapped=int(mapped),
        metadata_only=int(meta),
        mapped_pct=pct,
        youtube_api_configured=bool(resolve.get("youtube_api_configured")),
        consecutive_blocks=int(resolve.get("consecutive_blocks") or 0),
        block_cooldown_seconds=float(resolve.get("block_cooldown_seconds") or 0),
        last_resolve_batch=last if last.get("at") else None,
        hint=hint,
    )


@router.post("/enrich/run")
async def enrich_run(
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    from app.services.enrich import enrich_batch

    return await enrich_batch(db, limit=limit)


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
    if body.popularity_min is not None and body.popularity_max is not None:
        lo = min(body.popularity_min, body.popularity_max)
        hi = max(body.popularity_min, body.popularity_max)
        query = query.filter(Song.popularity.between(lo, hi))
    elif body.popularity_min is not None:
        query = query.filter(Song.popularity >= body.popularity_min)
    elif body.popularity_max is not None:
        query = query.filter(Song.popularity <= body.popularity_max)
    if body.only_mapped:
        query = query.filter(Song.youtube_video_id.isnot(None))
    if body.languages:
        terms = _language_match_terms(body.languages)
        if terms:
            query = query.filter(
                or_(*[Song.language.ilike(f"%{term}%") for term in terms])
            )
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
        db,
        limit=body.limit,
        composer=body.composer,
        dry_run=body.dry_run,
        source="manual",
    )


@router.post("/playlists/export", response_model=PlaylistExportResponse)
def playlists_export(body: PlaylistExportRequest, db: Session = Depends(get_db)):
    """Build a YouTube playlist payload from mapped library songs."""
    return export_playlist(db, body)


@router.post("/resolve/popularity")
async def resolve_popularity(
    limit: int = Query(default=25, ge=1, le=100),
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Refresh popularity scores from YouTube view counts for mapped songs."""
    return await refresh_popularity_from_views(db, limit=limit, force=force)
