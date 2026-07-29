from app.infrastructure.external.songs_library_client import LibrarySong, SongsLibraryClient


def test_library_song_from_dict_and_search_query():
    song = LibrarySong.from_dict(
        {
            "id": "abc",
            "song_name": "Thenpandi Cheemayile",
            "movie_name": "Nayakan",
            "composer_name": "Ilaiyaraaja",
            "singers": ["Kamal Haasan"],
            "content_hash": "hash1",
            "popularity": 90,
        }
    )
    assert song.song_name == "Thenpandi Cheemayile"
    assert "Nayakan" in song.search_query()
    assert "official audio" in song.search_query()


def test_client_disabled_without_url(monkeypatch):
    monkeypatch.setattr(
        "app.infrastructure.external.songs_library_client.settings.songs_library_url",
        "",
    )
    monkeypatch.setattr(
        "app.infrastructure.external.songs_library_client.settings.songs_library_enabled",
        True,
    )
    client = SongsLibraryClient(base_url="")
    assert client.enabled is False


async def test_resolve_youtube_many_parallel_and_skips_failures(monkeypatch):
    monkeypatch.setattr(
        "app.infrastructure.external.songs_library_client.settings.songs_library_enabled",
        True,
    )
    client = SongsLibraryClient(base_url="http://library.test")

    async def fake_one(song_id: str):
        if song_id == "fail":
            return None
        return LibrarySong(
            id=song_id,
            song_name=song_id,
            youtube_video_id=f"vid_{song_id}"[:11].ljust(11, "x"),
            playability="mapped",
        )

    monkeypatch.setattr(client, "resolve_youtube_for_song", fake_one)
    out = await client.resolve_youtube_many(["a", "fail", "b", "a"], concurrency=2)
    assert set(out) == {"a", "b"}
    assert out["a"].youtube_video_id
    assert "fail" not in out


async def test_sample_retries_on_502(monkeypatch):
    monkeypatch.setattr(
        "app.infrastructure.external.songs_library_client.settings.songs_library_enabled",
        True,
    )
    client = SongsLibraryClient(base_url="http://library.test")
    calls = {"n": 0}

    class FakeResp:
        def __init__(self, status_code: int, payload=None):
            self.status_code = status_code
            self._payload = payload or []

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "err",
                    request=httpx.Request("POST", "http://library.test/api/sample"),
                    response=httpx.Response(self.status_code),
                )

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            return FakeResp(200, {"status": "ok"})

        async def request(self, method, url, json=None):
            calls["n"] += 1
            if calls["n"] < 3:
                return FakeResp(502)
            return FakeResp(
                200,
                [{"id": "1", "song_name": "Song", "youtube_video_id": "abcdefghijk"}],
            )

    import httpx
    from app.infrastructure.external import songs_library_client as mod

    monkeypatch.setattr(mod.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(mod.asyncio, "sleep", lambda *_: _async_noop())

    async def _async_noop():
        return None

    # Replace sleep with immediate awaitable
    async def instant_sleep(*_args, **_kwargs):
        return None

    monkeypatch.setattr(mod.asyncio, "sleep", instant_sleep)

    songs = await client.sample(seed="Rahman", limit=1)
    assert calls["n"] == 3
    assert len(songs) == 1
    assert songs[0].song_name == "Song"