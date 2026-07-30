from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app


class _ScalarQuery:
    def __init__(self, value):
        self._value = value

    def filter(self, *_a, **_k):
        return self

    def scalar(self):
        return self._value


class _FakeDb:
    def __init__(self, total=100, mapped=10, meta=90):
        self._total = total
        self._mapped = mapped
        self._meta = meta
        self._calls = 0

    def query(self, *_a, **_k):
        self._calls += 1
        # Order: total, mapped, metadata_only
        if self._calls == 1:
            return _ScalarQuery(self._total)
        if self._calls == 2:
            return _ScalarQuery(self._mapped)
        return _ScalarQuery(self._meta)


def test_workers_status_endpoint(monkeypatch):
    monkeypatch.setattr(
        "app.routers.api.get_resolve_status",
        lambda: {
            "youtube_api_configured": True,
            "consecutive_blocks": 0,
            "block_cooldown_seconds": 0.0,
            "last_batch": {
                "at": "2026-07-30T10:00:00+00:00",
                "source": "background",
                "attempted": 10,
                "resolved": 2,
                "failed": 8,
            },
        },
    )

    def override_db():
        yield _FakeDb()

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            resp = client.get("/api/workers/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mapped"] == 10
        assert data["metadata_only"] == 90
        assert data["youtube_api_configured"] is True
        assert data["last_resolve_batch"]["resolved"] == 2
        assert data["mapped_pct"] == 10.0
    finally:
        app.dependency_overrides.clear()
