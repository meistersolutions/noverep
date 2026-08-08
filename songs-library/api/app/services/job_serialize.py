"""Serialize discover jobs without shipping fat cursor_json (Neon egress)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import DiscoverJob, DiscoverJobPage
from app.schemas import DiscoverJobOut, DiscoverJobPageOut, DiscoverJobPagesOut


def _titles(value) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            title = item.get("title") or item.get("name")
            if isinstance(title, str) and title.strip():
                out.append(title.strip())
    return out


def serialize_discover_job(job: DiscoverJob, db: Session | None = None) -> DiscoverJobOut:
    cursor = job.cursor_json if isinstance(job.cursor_json, dict) else {}
    queue = cursor.get("queue") or []
    seen = cursor.get("seen") or []
    page_count = len(_titles(cursor.get("wiki_list_pages")))
    if db is not None:
        page_count = (
            db.query(DiscoverJobPage)
            .filter(DiscoverJobPage.job_id == job.id)
            .count()
        )
    return DiscoverJobOut(
        id=job.id,
        seed=job.seed,
        status=job.status,
        phase=job.phase,
        entity_id=job.entity_id,
        entity_label=job.entity_label,
        found=job.found or 0,
        inserted=job.inserted or 0,
        skipped=job.skipped or 0,
        updated=job.updated or 0,
        pages_done=job.pages_done or 0,
        message=job.message,
        error=job.error,
        film_index=cursor.get("film_index"),
        films_total=cursor.get("films_total"),
        queue_len=len(queue) if isinstance(queue, list) else None,
        seen_len=len(seen) if isinstance(seen, (list, set, dict)) else None,
        wiki_list_page_count=int(page_count or 0),
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


def serialize_discover_job_pages(job: DiscoverJob, db: Session) -> DiscoverJobPagesOut:
    rows = (
        db.query(DiscoverJobPage)
        .filter(DiscoverJobPage.job_id == job.id)
        .order_by(DiscoverJobPage.processed_at.desc())
        .all()
    )
    pages = [
        DiscoverJobPageOut(
            title=row.page_title,
            kind=row.page_kind,
            songs_fetched=int(row.songs_fetched or 0),
            url=row.page_url,
        )
        for row in rows
    ]
    # Group legacy title lists by kind for any old UI still reading them.
    by_kind: dict[str, list[str]] = {
        "hub": [],
        "person": [],
        "film": [],
        "soundtrack": [],
        "other": [],
    }
    for page in pages:
        bucket = by_kind.get(page.kind) if page.kind in by_kind else by_kind["other"]
        bucket.append(page.title)
    return DiscoverJobPagesOut(
        id=job.id,
        pages=pages,
        wiki_list_pages=by_kind["hub"] + by_kind["person"] + by_kind["other"],
        filmography_pages=[],
        film_pages=by_kind["film"] + by_kind["soundtrack"],
    )
