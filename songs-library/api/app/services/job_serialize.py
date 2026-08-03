"""Serialize discover jobs without shipping fat cursor_json (Neon egress)."""

from __future__ import annotations

from app.models import DiscoverJob
from app.schemas import DiscoverJobOut, DiscoverJobPagesOut


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


def serialize_discover_job(job: DiscoverJob) -> DiscoverJobOut:
    cursor = job.cursor_json if isinstance(job.cursor_json, dict) else {}
    queue = cursor.get("queue") or []
    seen = cursor.get("seen") or []
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
        wiki_list_page_count=len(_titles(cursor.get("wiki_list_pages"))),
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


def serialize_discover_job_pages(job: DiscoverJob) -> DiscoverJobPagesOut:
    cursor = job.cursor_json if isinstance(job.cursor_json, dict) else {}
    return DiscoverJobPagesOut(
        id=job.id,
        wiki_list_pages=_titles(cursor.get("wiki_list_pages")),
        filmography_pages=_titles(cursor.get("filmography_pages")),
        film_pages=_titles(cursor.get("film_pages")),
    )
