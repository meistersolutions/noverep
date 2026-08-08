from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.config import settings
from app.db import SessionLocal
from app.models import DiscoverJob
from app.services.discover import merge_and_upsert_works, resolve_seed_meta
from app.services.discover_pages import clear_discover_job_pages, upsert_discover_job_page
from app.services import enrich, wiki_crawl
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
        clear_discover_job_pages(db, job.id)
    else:
        pages = int((job.cursor_json or {}).get("pages_done") or job.pages_done or 0)
        job.message = (
            f"Resume queued by user (continuing after {pages} pages)"
            if pages > 0
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
        # New BFS cursor uses queue/seen; legacy film_index-only cursors start fresh.
        bfs_cursor = None
        if prev_cursor.get("queue") is not None or prev_cursor.get("seen"):
            bfs_cursor = prev_cursor
        is_resume = bool(bfs_cursor)

        job.status = "running"
        job.phase = "resolve"
        job.finished_at = None
        job.message = (
            f"Resuming Wikipedia crawl ({int(prev_cursor.get('pages_done') or 0)} pages done)…"
            if is_resume
            else "Searching Wikipedia for seed…"
        )
        db.commit()
        qid, label = await resolve_seed_meta(job.seed)
        job = _reload_active_job(db, job_id)
        if not job:
            return
        job.entity_id = qid
        job.entity_label = label
        job.phase = "wikipedia_bfs"
        job.message = f"Crawling Wikipedia from {label or job.seed}…"
        db.commit()

        commit_every = max(1, int(settings.discover_queue_batch_commit))
        pages_since_commit = 0

        async def on_progress(state: dict) -> None:
            nonlocal pages_since_commit, job
            job = _reload_active_job(db, job_id)
            if not job:
                raise asyncio.CancelledError()
            delta = list(state.get("works_delta") or [])
            if delta:
                stats = merge_and_upsert_works(
                    db,
                    works=delta,
                    seed=job.seed,
                    entity_qid=qid,
                    composer_name=None,
                )
                job.inserted = int(job.inserted or 0) + int(stats["inserted"])
                job.skipped = int(job.skipped or 0) + int(stats["skipped"])
                job.updated = int(job.updated or 0) + int(stats["updated"])
                job.found = int(job.found or 0) + int(stats["found"])
            kind = state.get("kind") or ""
            page = state.get("current_page") or ""
            if page:
                upsert_discover_job_page(
                    db,
                    job_id=job_id,
                    page_title=page,
                    page_kind=kind or "other",
                    songs_fetched=len(delta),
                )
            cursor = {
                "queue": state.get("queue") or [],
                "seen": state.get("seen") or [],
                "pages_done": state.get("pages_done") or 0,
                "seed_pages": state.get("seed_pages") or [],
                "film_pages": state.get("film_pages") or [],
                "hub_pages": state.get("hub_pages") or [],
                "films_total": state.get("films_total") or 0,
                "film_index": state.get("film_index") or 0,
            }
            job.cursor_json = cursor
            job.pages_done = int(cursor["pages_done"])
            job.message = (
                f"{kind}: {page} "
                f"(pages {job.pages_done}, inserted {job.inserted})"
            )
            pages_since_commit += 1
            if pages_since_commit >= commit_every or delta:
                db.commit()
                pages_since_commit = 0

        if not is_resume:
            job.found = 0
            job.inserted = 0
            job.skipped = 0
            job.updated = 0
            db.commit()

        try:
            result = await wiki_crawl.crawl_seed_bfs(
                job.seed,
                cursor=bfs_cursor,
                on_progress=on_progress,
            )
        except asyncio.CancelledError:
            return

        job = _reload_active_job(db, job_id)
        if not job:
            return
        job.cursor_json = result.get("cursor") or job.cursor_json
        job.pages_done = int(result.get("pages_done") or job.pages_done or 0)
        # If crawl returned works that somehow weren't flushed (empty progress), upsert once.
        # Incremental path already persisted deltas; avoid double-counting by only
        # upserting when nothing was inserted this run and works exist.
        remaining_queue = (job.cursor_json or {}).get("queue") or []
        if remaining_queue and settings.discover_max_pages and job.pages_done >= settings.discover_max_pages:
            job.phase = "paused_budget"
            job.status = "pending"
            job.message = (
                f"Page budget reached ({job.pages_done}); re-queued to continue"
            )
            job.finished_at = None
            db.commit()
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


async def noverep_keepalive_loop(stop_event: asyncio.Event) -> None:
    """Ping NoRepeat while Songs Library is awake (mutual free-tier keepalive)."""
    import logging

    import httpx

    log = logging.getLogger(__name__)
    url = (settings.noverep_keepalive_url or "").strip()
    if not url:
        return
    interval = max(60.0, float(settings.noverep_keepalive_seconds))
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


def worker_runtime_status() -> dict:
    """Inspect in-process background tasks (for portal / debugging stuck queues)."""
    tasks_out: list[dict] = []
    for task in _tasks:
        info: dict = {
            "name": task.get_name(),
            "done": task.done(),
            "cancelled": task.cancelled(),
        }
        if task.done() and not task.cancelled():
            exc = task.exception()
            if exc is not None:
                info["exception"] = f"{type(exc).__name__}: {exc}"
        tasks_out.append(info)
    return {
        "enabled": bool(settings.background_workers_enabled),
        "task_count": len(_tasks),
        "alive_count": sum(1 for t in _tasks if not t.done()),
        "tasks": tasks_out,
        "active_discover_jobs": sorted(_active_job_ids),
    }


def _log_task_done(task: asyncio.Task) -> None:
    import logging

    log = logging.getLogger(__name__)
    name = task.get_name()
    if task.cancelled():
        log.warning("background_worker_cancelled name=%s", name)
        return
    exc = task.exception()
    if exc is not None:
        log.exception("background_worker_crashed name=%s", name, exc_info=exc)
    else:
        log.info("background_worker_exited name=%s", name)


async def discover_queue_loop(stop_event: asyncio.Event) -> None:
    """Pick pending discover jobs and run them continuously."""
    import logging

    log = logging.getLogger(__name__)
    log.info("discover_queue_loop_started")
    # First tick: reclaim jobs left running after the last Render sleep/deploy.
    db = SessionLocal()
    try:
        n = reclaim_orphaned_running_jobs(db)
        if n:
            log.warning("reclaimed_orphaned_discover_jobs count=%s", n)
    except Exception:  # noqa: BLE001
        log.exception("discover_queue_reclaim_failed")
    finally:
        db.close()

    while not stop_event.is_set():
        job_id = None
        try:
            db = SessionLocal()
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
                    log.info("discover_queue_claim job_id=%s seed=%s", job_id, job.seed)
            finally:
                db.close()
            if job_id:
                await run_discover_job(job_id)
            else:
                await asyncio.sleep(max(2.0, float(settings.discover_queue_idle_seconds)))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("discover_queue_loop_error")
            await asyncio.sleep(5.0)


async def enrich_loop(stop_event: asyncio.Event) -> None:
    """Background thread: keep filling missing singers/lyricists."""
    import logging

    log = logging.getLogger(__name__)
    log.info("enrich_loop_started")
    while not stop_event.is_set():
        db = SessionLocal()
        try:
            result = await enrich.enrich_batch(db, limit=settings.enrich_batch_size)
            if result["checked"] == 0:
                await asyncio.sleep(settings.enrich_idle_seconds)
            else:
                await asyncio.sleep(settings.enrich_pause_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("enrich_loop_error")
            await asyncio.sleep(5)
        finally:
            db.close()


async def youtube_resolve_loop(stop_event: asyncio.Event) -> None:
    """Background: map unmapped songs, then refresh popularity from YouTube views."""
    import logging

    from app.services.youtube_resolve import youtube_block_cooldown_seconds

    log = logging.getLogger(__name__)
    log.info("youtube_resolve_loop_started")
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
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("youtube_resolve_loop_error")
            await asyncio.sleep(5)
        finally:
            db.close()


async def semantic_enrich_loop(stop_event: asyncio.Event) -> None:
    """Background: lyrics + LLM tags/summary + local embeddings."""
    import logging

    from app.services import llm_client
    from app.services.semantic_enrich import enrich_batch

    log = logging.getLogger(__name__)
    log.info("semantic_enrich_loop_started")
    while not stop_event.is_set():
        if not settings.semantic_enrich_enabled or not llm_client.llm_configured():
            await asyncio.sleep(settings.semantic_enrich_idle_seconds)
            continue
        db = SessionLocal()
        try:
            result = await enrich_batch(db, limit=settings.semantic_enrich_batch_size)
            if result.get("checked", 0) == 0:
                await asyncio.sleep(settings.semantic_enrich_idle_seconds)
            else:
                await asyncio.sleep(settings.semantic_enrich_pause_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("semantic_enrich_loop_error")
            await asyncio.sleep(5)
        finally:
            db.close()


def start_background_workers() -> None:
    global _stop, _tasks
    import logging

    log = logging.getLogger(__name__)
    # Drop finished/crashed tasks so a restart can recreate them.
    _tasks = [t for t in _tasks if not t.done()]
    if _tasks:
        log.info("background_workers_already_running count=%s", len(_tasks))
        return
    if not settings.background_workers_enabled:
        log.warning(
            "background_workers_disabled — set BACKGROUND_WORKERS_ENABLED=true to resume"
        )
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        log.error("background_workers_skipped — no running event loop at startup")
        return
    _stop = asyncio.Event()
    _tasks = [
        asyncio.create_task(discover_queue_loop(_stop), name="discover-queue"),
        asyncio.create_task(enrich_loop(_stop), name="enrich-loop"),
        asyncio.create_task(youtube_resolve_loop(_stop), name="youtube-resolve"),
        asyncio.create_task(semantic_enrich_loop(_stop), name="semantic-enrich"),
        asyncio.create_task(noverep_keepalive_loop(_stop), name="noverep-keepalive"),
    ]
    for task in _tasks:
        task.add_done_callback(_log_task_done)
    log.info("background_workers_started count=%s", len(_tasks))


def stop_background_workers() -> None:
    global _stop, _tasks
    if _stop:
        _stop.set()
    for task in _tasks:
        task.cancel()
    _tasks = []
