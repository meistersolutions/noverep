"""Status codes for POST /api/songs/{id}/resolve-youtube."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.routers import api as api_router


class _FakeQuery:
    def __init__(self, song):
        self._song = song

    def filter(self, *_args, **_kwargs):
        return self

    def one_or_none(self):
        return self._song


class _FakeDb:
    def __init__(self, song):
        self._song = song

    def query(self, *_args, **_kwargs):
        return _FakeQuery(self._song)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_resolve_youtube_song_not_found(client):
    def override_db():
        yield _FakeDb(None)

    app.dependency_overrides[get_db] = override_db
    resp = client.post("/api/songs/missing-id/resolve-youtube")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Song not found"


def test_resolve_youtube_resolve_failed(client, monkeypatch):
    song = SimpleNamespace(
        id="song-1",
        song_name="Test",
        movie_name=None,
        composer_name=None,
        youtube_video_id=None,
    )

    def override_db():
        yield _FakeDb(song)

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(
        api_router,
        "resolve_one_song",
        AsyncMock(return_value=None),
    )
    resp = client.post("/api/songs/song-1/resolve-youtube")
    assert resp.status_code == 422
    assert "Could not resolve" in resp.json()["detail"]
