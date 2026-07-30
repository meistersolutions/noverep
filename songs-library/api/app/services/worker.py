from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.config import settings
from app.db import SessionLocal
from app.models import DiscoverJob
from app.services.discover import merge_and_upsert_works, resolve_seed_meta
from app.services import enrich, musicbrainz, wikipedia, wikidata
from app.services.youtube_resolve import resolve_unmapped, refresh_popularity_from_views


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_stopped(status: str | None) -> bool:
    return (status or "").lower() in {"cancelled", "archived"}


# Jobs currently executing in this process (survives only until pod sleep/restart).
_active_job_ids: set[str] = set()


def reclaim_orphaned_running_jobs(db: Session) -> int:
    """Re-queue discover jobs left 'running' after a process death / Render sleep.

    The queue loop only picks ``pending`` jobs, so orphaned ``running`` rows
    would otherwise sit forever.
    """
    orphans = (
        db.query(DiscoverJob)
        .filter(DiscoverJob.status == "running")
        .all()
    )
    reclaimed = 0
    for job in orphans:
        if job.id in _active_job_ids:
            continue
        job.status = "pending"
        job.phase = "queued"
        job.message = "Requeued after worker restart (was stuck running)"
        job.finished_at = None
        job.error = None
        reclaimed += 1
    if reclaimed:
        db.commit()
    return reclaimed


def requeue_discover_job(db: Session, job: DiscoverJob, *, reset_progress: bool = False) -> DiscoverJob:
    """Put a job back on the pending queue so the background worker can run it."""
    job.status = "pending"
    job.phase = "queued"
    job.finished_at = None
    job.error = None
    if reset_progress:
        job.found = 0
        job.inserted = 0
        job.skipped = 0
        job.updated = 0
        job.pages_done = 0
        job.cursor_json = None
        job.message = "Restarted from the beginning by user"
    else:
        film_i = int((job.cursor_json or {}).get("film_index") or 0)
        job.message = (
            f"Resume queued by user (continuing after film {film_i})"
            if film_i > 0
            else "Resume queued by user"
        )
    db.commit()
    db.refresh(job)
    return job


def _reload_active_job(db: Session, job_id: str) -> DiscoverJob | None:
    """Return the job if it is still allowed to run; else None."""
    job = db.query(DiscoverJob).filter(DiscoverJob.id == job_id).one_or_none()
    if not job or _is_stopped(job.status):
        return None
    # User requeued while we were mid-run — stop this execution.
    if job.status == "pending" and job_id in _active_job_ids:
        return None
    if job.status not in {"running", "pending"}:
        return None
    return job


async def run_discover_job(job_id: str) -> None:
    db = SessionLocal()
    _active_job_ids.add(job_id)
    try:
        job = db.query(DiscoverJob).filter(DiscoverJob.id == job_id).one_or_none()
        if not job or _is_stopped(job.status):
            return
        prev_cursor = dict(job.cursor_json or {})
        resume_film_index = int(prev_cursor.get("film_index") or 0)
        prior_inserted = int(job.inserted or 0)
        is_resume = resume_film_index > 0 or prior_inserted > 0

        job.status = "running"
        job.phase = "resolve"
        job.finished_at = None
        job.message = (
            f"Resuming after film {resume_film_index}…"
            if resume_film_index > 0
            else "Resolving composer…"
        )
        db.commit()
        qid, label = await resolve_seed_meta(job.seed)
        job = _reload_active_job(db, job_id)
        if not job:
            return
        composer_name = label or job.seed.strip()
        job.entity_id = qid
        job.entity_label = label
        job.phase = "wikipedia_lists"
        job.message = f"Scanning Wikipedia song lists for {composer_name}…"
        db.commit()
        # Phase 1: full Wikipedia song-list pages (no artificial cap).
        wiki_works, list_pages = await wikipedia.fetch_composer_songs_detailed(
            composer_name, limit=None
        )
        job = _reload_active_job(db, job_id)
        if not job:
            return
        cursor: dict = {
            "wiki_list_pages": list_pages,
            "filmography_pages": list(prev_cursor.get("filmography_pages") or []),
            "film_pages": list(prev_cursor.get("film_pages") or []),
            "film_index": resume_film_index,
            "films_total": int(prev_cursor.get("films_total") or 0),
        }
        job.cursor_json = dict(cursor)
        db.commit()
        wd_works: list[dict] = []
        if qid:
            try:
                wd_works = await wikidata.fetch_composer_works(
                    qid, limit=settings.discover_wikidata_limit
                )
                for w in wd_works:
                    w.setdefault("source", "wikidata_sparql")
            except Exception as exc:  # noqa: BLE001
                job = _reload_active_job(db, job_id)
                if not job:
                    return
                job.message = f"Wikidata partial failure: {exc}"
        job = _reload_active_job(db, job_id)
        if not job:
            return
        for w in wiki_works:
            w.setdefault("source", "wikipedia")
        stats = merge_and_upsert_works(
            db,
            works=wiki_works + wd_works,
            composer_name=composer_name,
            seed=job.seed,
            entity_qid=qid,
        )
        if is_resume:
            # Keep counters from the interrupted run; only add new deltas.
            job.inserted = prior_inserted + int(stats["inserted"])
            job.skipped = int(job.skipped or 0) + int(stats["skipped"])
            job.updated = int(job.updated or 0) + int(stats["updated"])
            job.found = max(int(job.found or 0), int(stats["found"]))
        else:
            job.found = stats["found"]
            job.inserted = stats["inserted"]
            job.skipped = stats["skipped"]
            job.updated = stats["updated"]
        job.pages_done = len(list_pages) or 1
        job.cursor_json = dict(cursor)
        db.commit()
        job = _reload_active_job(db, job_id)
        if not job:
            return
        # Phase 2: page-to-page film soundtrack crawl.
        job.phase = "wikipedia_films"
        job.message = "Walking filmography pages for soundtrack tables…"
        db.commit()
        try:
            films, filmography_pages = await wikipedia.list_composer_films(composer_name)
        except Exception as exc:  # noqa: BLE001
            films = []
            filmography_pages = []
            job = _reload_active_job(db, job_id)
            if not job:
                return
            job.message = f"Film list failed: {exc}"
            db.commit()
        job = _reload_active_job(db, job_id)
        if not job:
            return
        cursor["filmography_pages"] = filmography_pages
        cursor["films_total"] = len(films)
        # Resume mid-list after Render sleep / manual requeue.
        start_at = min(max(resume_film_index, 0), len(films))
        cursor["film_index"] = start_at
        job.cursor_json = dict(cursor)
        if start_at > 0:
            job.message = (
                f"Resuming film crawl at {start_at + 1}/{len(films)}…"
            )
        db.commit()
        batch = settings.discover_films_per_tick
        film_pages: list[str] = list(cursor.get("film_pages") or [])
        for i, film in enumerate(films):
            if i < start_at:
                continue
            job = _reload_active_job(db, job_id)
            if not job:
                return
            cursor["film_index"] = i + 1
            job.cursor_json = dict(cursor)
            job.pages_done = len(list_pages) + i + 1
            job.message = (
                f"Film {i + 1}/{len(films)}: {film.get('film')} "
                f"(inserted {job.inserted} so far)"
            )
            db.commit()
            try:
                works, film_page = await wikipedia.fetch_film_soundtrack_songs(
                    film["film"], year=film.get("year")
                )
            except Exception:  # noqa: BLE001
                works, film_page = [], None
            job = _reload_active_job(db, job_id)
            if not job:
                return
            if film_page and film_page not in film_pages:
                film_pages.append(film_page)
                cursor["film_pages"] = film_pages
            if works:
                stats = merge_and_upsert_works(
                    db,
                    works=works,
                    composer_name=composer_name,
                    seed=job.seed,
                    entity_qid=qid,
                )
                job.inserted += stats["inserted"]
                job.skipped += stats["skipped"]
                job.updated += stats["updated"]
                job.found += stats["found"]
                job.cursor_json = dict(cursor)
                db.commit()
            await asyncio.sleep(0.25)
            # Keep event loop responsive; still continuous within one job.
            if (i + 1) % batch == 0:
                await asyncio.sleep(0.05)
        job = _reload_active_job(db, job_id)
        if not job:
            return
        cursor["film_pages"] = film_pages
        job.cursor_json = dict(cursor)
        db.commit()
        # Phase 3: MusicBrainz pagination.
        job.phase = "musicbrainz"
        job.message = "Paging MusicBrainz works…"
        db.commit()
        try:
            mb_id, _ = await musicbrainz.resolve_artist_id(composer_name)
            job = _reload_active_job(db, job_id)
            if not job:
                return
            if mb_id:
                mb_works = await musicbrainz.fetch_artist_works(
                    mb_id, limit=settings.discover_musicbrainz_limit
                )
                job = _reload_active_job(db, job_id)
                if not job:
                    return
                stats = merge_and_upsert_works(
                    db,
                    works=mb_works,
                    composer_name=composer_name,
                    seed=job.seed,
                    entity_qid=qid,
                )
                job.inserted += stats["inserted"]
                job.skipped += stats["skipped"]
                job.updated += stats["updated"]
                job.found += stats["found"]
        except Exception as exc:  # noqa: BLE001
            job = _reload_active_job(db, job_id)
            if not job:
                return
            job.message = f"MusicBrainz partial failure: {exc}"
        job = _reload_active_job(db, job_id)
        if not job:
            return
        job.phase = "done"
        job.status = "completed"
        job.message = (
            f"Done. inserted={job.inserted} updated={job.updated} skipped={job.skipped}"
        )
        job.finished_at = _utcnow()
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job = db.query(DiscoverJob).filter(DiscoverJob.id == job_id).one_or_none()
        if job and not _is_stopped(job.status):
            job.status = "failed"
            job.error = str(exc)
            job.message = str(exc)
            job.finished_at = _utcnow()
            db.commit()
    finally:
        _active_job_ids.discard(job_id)
        db.close()


async def enrich_loop(stop_event: asyncio.Event) -> None:
    """Background thread: keep filling missing singers/lyricists."""
    while not stop_event.is_set():
        db = SessionLocal()
        try:
            result = await enrich.enrich_batch(db, limit=settings.enrich_batch_size)
            if result["checked"] == 0:
                await asyncio.sleep(settings.enrich_idle_seconds)
            else:
                await asyncio.sleep(settings.enrich_pause_seconds)
        except Exception:  # noqa: BLE001
            await asyncio.sleep(5)
        finally:
            db.close()


async def youtube_resolve_loop(stop_event: asyncio.Event) -> None:
    """Background: map unmapped songs, then refresh popularity from YouTube views."""
    from app.services.youtube_resolve import youtube_block_cooldown_seconds

    while not stop_event.is_set():
        db = SessionLocal()
        try:
            result = await resolve_unmapped(
                db,
                limit=settings.youtube_resolve_batch_size,
                dry_run=False,
                source="background",
            )
            if result.attempted == 0:
                stats = await refresh_popularity_from_views(
                    db,
                    limit=settings.youtube_resolve_batch_size,
                    force=False,
                )
                if stats["attempted"] == 0:
                    await asyncio.sleep(settings.youtube_resolve_idle_seconds)
                else:
                    await asyncio.sleep(settings.youtube_resolve_pause_seconds)
            else:
                pause = settings.youtube_resolve_pause_seconds
                # If the whole batch failed, YouTube is likely blocking this host.
                if result.resolved == 0 and result.failed > 0:
                    pause = max(pause, youtube_block_cooldown_seconds())
                await asyncio.sleep(pause)
        except Exception:  # noqa: BLE001
            await asyncio.sleep(5)
        finally:
            db.close()


async def discover_queue_loop(stop_event: asyncio.Event) -> None:
    """Pick pending discover jobs and run them continuously."""
    # First tick: reclaim jobs left running after the last Render sleep/deploy.
    db = SessionLocal()
    try:
        n = reclaim_orphaned_running_jobs(db)
        if n:
            import logging

            logging.getLogger(__name__).warning("reclaimed_orphaned_discover_jobs", extra={"count": n})
    finally:
        db.close()

    while not stop_event.is_set():
        db = SessionLocal()
        job_id = None
        try:
            reclaim_orphaned_running_jobs(db)
            job = (
                db.query(DiscoverJob)
                .filter(DiscoverJob.status == "pending")
                .order_by(DiscoverJob.created_at.asc())
                .first()
            )
            if job:
                job_id = job.id
        finally:
            db.close()
        if job_id:
            await run_discover_job(job_id)
        else:
            await asyncio.sleep(2.0)


async def noverep_keepalive_loop(stop_event: asyncio.Event) -> None:
    """Ping NoRepeat while Songs Library is awake (mutual free-tier keepalive)."""
    import logging

    import httpx

    log = logging.getLogger(__name__)
    url = (settings.noverep_keepalive_url or "").strip()
    if not url:
        return
    interval = max(30.0, float(settings.noverep_keepalive_seconds))
    log.info("noverep_keepalive_started url=%s interval=%s", url, interval)
    while not stop_event.is_set():
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(url)
                log.info("noverep_keepalive_ping status=%s", resp.status_code)
        except Exception as exc:  # noqa: BLE001
            log.warning("noverep_keepalive_ping_failed error=%s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            break
        except TimeoutError:
            pass


_stop: asyncio.Event | None = None
_tasks: list[asyncio.Task] = []


def start_background_workers() -> None:
    global _stop, _tasks
    if _tasks:
        return
    _stop = asyncio.Event()
    _tasks = [
        asyncio.create_task(discover_queue_loop(_stop), name="discover-queue"),
        asyncio.create_task(enrich_loop(_stop), name="enrich-loop"),
        asyncio.create_task(youtube_resolve_loop(_stop), name="youtube-resolve"),
        asyncio.create_task(noverep_keepalive_loop(_stop), name="noverep-keepalive"),
    ]


def stop_background_workers() -> None:
    global _stop, _tasks
    if _stop:
        _stop.set()
    for task in _tasks:
        task.cancel()
    _tasks = []
