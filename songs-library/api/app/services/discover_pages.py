"""Record Wikipedia pages processed during discover crawls."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.models import DiscoverJobPage


def wikipedia_page_url(title: str) -> str:
    slug = quote(str(title).replace(" ", "_"), safe=":_()/!'*,;")
    return f"https://en.wikipedia.org/wiki/{slug}"


def upsert_discover_job_page(
    db: Session,
    *,
    job_id: str,
    page_title: str,
    page_kind: str,
    songs_fetched: int,
) -> DiscoverJobPage | None:
    title = (page_title or "").strip()
    if not title or not job_id:
        return None
    kind = (page_kind or "other").strip() or "other"
    count = max(0, int(songs_fetched or 0))
    now = datetime.now(timezone.utc)

    row = (
        db.query(DiscoverJobPage)
        .filter(
            DiscoverJobPage.job_id == job_id,
            DiscoverJobPage.page_title == title,
        )
        .one_or_none()
    )
    if row:
        row.page_kind = kind
        row.page_url = wikipedia_page_url(title)
        # Keep the higher count if a page is revisited with more extractions.
        row.songs_fetched = max(int(row.songs_fetched or 0), count)
        row.processed_at = now
        return row

    row = DiscoverJobPage(
        job_id=job_id,
        page_title=title,
        page_kind=kind,
        page_url=wikipedia_page_url(title),
        songs_fetched=count,
        processed_at=now,
    )
    db.add(row)
    return row


def clear_discover_job_pages(db: Session, job_id: str) -> int:
    if not job_id:
        return 0
    deleted = (
        db.query(DiscoverJobPage)
        .filter(DiscoverJobPage.job_id == job_id)
        .delete(synchronize_session=False)
    )
    return int(deleted or 0)
