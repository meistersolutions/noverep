"""Unit tests for Songs Library keepalive loop."""

import asyncio

import pytest


@pytest.mark.asyncio
async def test_keepalive_loop_pings_then_stops(monkeypatch):
    from app.application.tasks import songs_library_keepalive as mod

    monkeypatch.setattr(mod.settings, "songs_library_enabled", True)
    monkeypatch.setattr(mod.settings, "songs_library_url", "https://songs-library.test")
    monkeypatch.setattr(mod.settings, "songs_library_keepalive_seconds", 30)

    calls = {"n": 0}

    class FakeClient:
        async def health(self):
            calls["n"] += 1
            return True

    monkeypatch.setattr(mod, "SongsLibraryClient", FakeClient)

    stop = asyncio.Event()

    async def run():
        task = asyncio.create_task(mod.songs_library_keepalive_loop(stop))
        # Allow boot ping
        await asyncio.sleep(0.05)
        assert calls["n"] >= 1
        stop.set()
        await task

    await run()


@pytest.mark.asyncio
async def test_keepalive_disabled_when_library_off(monkeypatch):
    from app.application.tasks import songs_library_keepalive as mod

    monkeypatch.setattr(mod.settings, "songs_library_enabled", False)
    monkeypatch.setattr(mod.settings, "songs_library_url", "https://songs-library.test")

    stop = asyncio.Event()
    await mod.songs_library_keepalive_loop(stop)
