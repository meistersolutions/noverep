from types import SimpleNamespace

from app.services.worker import reclaim_orphaned_running_jobs, requeue_discover_job


class _FakeQuery:
    def __init__(self, jobs):
        self._jobs = jobs

    def filter(self, *_a, **_k):
        return self

    def all(self):
        return list(self._jobs)


class _FakeDb:
    def __init__(self, jobs):
        self.jobs = jobs
        self.committed = False

    def query(self, *_a, **_k):
        return _FakeQuery(self.jobs)

    def commit(self):
        self.committed = True

    def refresh(self, job):
        return job


def test_reclaim_orphaned_running_jobs():
    running = SimpleNamespace(
        id="a",
        status="running",
        phase="wikipedia_films",
        message="Film 3/10",
        finished_at=None,
        error=None,
    )
    db = _FakeDb([running])
    n = reclaim_orphaned_running_jobs(db)
    assert n == 1
    assert running.status == "pending"
    assert db.committed is True


def test_requeue_preserves_progress_by_default():
    job = SimpleNamespace(
        id="b",
        status="running",
        phase="wikipedia_films",
        found=10,
        inserted=5,
        skipped=2,
        updated=1,
        pages_done=3,
        cursor_json={"film_index": 12, "films_total": 100},
        message="old",
        finished_at="x",
        error="e",
    )
    db = _FakeDb([])
    out = requeue_discover_job(db, job, reset_progress=False)
    assert out.status == "pending"
    assert out.inserted == 5
    assert out.cursor_json["film_index"] == 12
    assert "Resume" in out.message
