from types import SimpleNamespace

from app.services.discover_pages import (
    clear_discover_job_pages,
    upsert_discover_job_page,
    wikipedia_page_url,
)


class _FakeQuery:
    def __init__(self, rows):
        self._rows = list(rows)
        self._filters = []

    def filter(self, *args, **_k):
        self._filters.extend(args)
        return self

    def one_or_none(self):
        if not self._rows:
            return None
        # Simple match: return first row with same title when filtering by title.
        return self._rows[0] if self._rows else None

    def delete(self, synchronize_session=False):
        n = len(self._rows)
        self._rows.clear()
        return n


class _FakeDb:
    def __init__(self):
        self.rows = []
        self.added = []

    def query(self, model):
        return _FakeQuery(self.rows)

    def add(self, row):
        self.added.append(row)
        self.rows.append(row)


def test_wikipedia_page_url_spaces():
    assert wikipedia_page_url("A. R. Rahman") == "https://en.wikipedia.org/wiki/A._R._Rahman"


def test_upsert_discover_job_page_inserts():
    db = _FakeDb()
    row = upsert_discover_job_page(
        db,
        job_id="job-1",
        page_title="Roja (film)",
        page_kind="film",
        songs_fetched=3,
    )
    assert row is not None
    assert len(db.added) == 1
    assert row.page_title == "Roja (film)"
    assert row.page_kind == "film"
    assert row.songs_fetched == 3
    assert "Roja_(film)" in row.page_url


def test_upsert_discover_job_page_updates_existing():
    existing = SimpleNamespace(
        job_id="job-1",
        page_title="Roja (film)",
        page_kind="other",
        page_url="https://en.wikipedia.org/wiki/old",
        songs_fetched=1,
        processed_at=None,
    )
    db = _FakeDb()
    db.rows = [existing]
    row = upsert_discover_job_page(
        db,
        job_id="job-1",
        page_title="Roja (film)",
        page_kind="film",
        songs_fetched=5,
    )
    assert row is existing
    assert row.page_kind == "film"
    assert row.songs_fetched == 5
    assert len(db.added) == 0


def test_clear_discover_job_pages():
    db = _FakeDb()
    db.rows = [SimpleNamespace(job_id="job-1")]
    assert clear_discover_job_pages(db, "job-1") == 1
