"""Tests for GET /api/composers."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def group_by(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(self, composer_rows):
        self._composer_rows = composer_rows

    def query(self, *args, **_kwargs):
        # stats() uses scalar(); composers list uses grouped rows.
        if len(args) == 1:
            scalar_mock = MagicMock()
            scalar_mock.scalar.return_value = 0
            return scalar_mock
        return _FakeQuery(self._composer_rows)


def test_list_composers_returns_song_and_movie_counts():
    rows = [
        ("Ilaiyaraaja", 5095, 412),
        ("A. R. Rahman", 2350, 180),
        (None, 3, 0),
    ]

    def override_db():
        yield _FakeDb(rows)

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            resp = client.get("/api/composers")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0] == {
            "name": "Ilaiyaraaja",
            "song_count": 5095,
            "movie_count": 412,
        }
        assert data[-1]["name"] == "Unknown"
        assert data[-1]["song_count"] == 3
        assert data[-1]["movie_count"] == 0
    finally:
        app.dependency_overrides.clear()
