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


def _reload_active_job(db: Session, job_id: str) -> DiscoverJob | None:
    """Return the job if it is still allowed to run; else None."""
    job = db.query(DiscoverJob).filter(DiscoverJob.id == job_id).one_or_none()
    if not job or _is_stopped(job.status):
        return None
    return job


async def run_discover_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(DiscoverJob).filter(DiscoverJob.id == job_id).one_or_none()
        if not job or _is_stopped(job.status):
            return
        job.status = "running"
        job.phase = "resolve"
        job.message = "Resolving composer…"
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
            "filmography_pages": [],
            "film_pages": [],
            "film_index": 0,
            "films_total": 0,
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
        cursor["film_index"] = 0
        cursor["films_total"] = len(films)
        job.cursor_json = dict(cursor)
        db.commit()
        batch = settings.discover_films_per_tick
        film_pages: list[str] = []
        for i, film in enumerate(films):
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
    while not stop_event.is_set():
        db = SessionLocal()
        job_id = None
        try:
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
    ]


def stop_background_workers() -> None:
    global _stop, _tasks
    if _stop:
        _stop.set()
    for task in _tasks:
        task.cancel()
    _tasks = []
