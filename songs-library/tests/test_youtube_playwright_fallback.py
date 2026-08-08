"""Playwright fallback kicks in when yt-dlp fails and Data API is unset."""

from app.services import youtube_resolve as yr


def test_playwright_used_when_ytdlp_blocked(monkeypatch):
    monkeypatch.setattr(yr, "_youtube_api_key", lambda: "")
    monkeypatch.setattr(yr, "_search_via_data_api", lambda *a, **k: (None, None))
    monkeypatch.setattr(yr, "_ydl_opts", lambda **k: {})

    class BoomYDL:
        def __init__(self, *_a, **_k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def extract_info(self, *_a, **_k):
            raise Exception("HTTP Error 403: Forbidden")

    import yt_dlp

    monkeypatch.setattr(yt_dlp, "YoutubeDL", BoomYDL)
    monkeypatch.setattr(
        "app.services.youtube_playwright.search_youtube_playwright",
        lambda query: ("dQw4w9WgXcQ", 12345),
    )
    monkeypatch.setattr(yr.settings, "youtube_playwright_fallback", True)

    vid, views = yr._search_youtube_sync("test song movie composer", allow_playwright=True)
    assert vid == "dQw4w9WgXcQ"
    assert views == 12345


def test_playwright_skipped_on_secondary_query(monkeypatch):
    monkeypatch.setattr(yr, "_youtube_api_key", lambda: "")
    monkeypatch.setattr(yr, "_search_via_data_api", lambda *a, **k: (None, None))
    monkeypatch.setattr(yr, "_ydl_opts", lambda **k: {})

    class EmptyYDL:
        def __init__(self, *_a, **_k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def extract_info(self, *_a, **_k):
            return {"entries": []}

    import yt_dlp

    monkeypatch.setattr(yt_dlp, "YoutubeDL", EmptyYDL)
    called = {"n": 0}

    def pw(_q):
        called["n"] += 1
        return ("dQw4w9WgXcQ", 1)

    monkeypatch.setattr("app.services.youtube_playwright.search_youtube_playwright", pw)
    monkeypatch.setattr(yr.settings, "youtube_playwright_fallback", True)
    vid, _views = yr._search_youtube_sync("secondary", allow_playwright=False)
    assert vid is None
    assert called["n"] == 0


def test_playwright_skipped_when_data_api_configured(monkeypatch):
    monkeypatch.setattr(yr, "_youtube_api_key", lambda: "fake-key")
    monkeypatch.setattr(yr, "_search_via_data_api", lambda *a, **k: (None, None))
    called = {"pw": False}

    def boom_pw(_q):
        called["pw"] = True
        return ("dQw4w9WgXcQ", 1)

    monkeypatch.setattr(
        "app.services.youtube_playwright.search_youtube_playwright",
        boom_pw,
    )
    vid, views = yr._search_youtube_sync("test")
    assert vid is None
    assert called["pw"] is False


def test_parse_view_count_helpers():
    from app.services.youtube_playwright import looks_like_video_id, parse_view_count

    assert parse_view_count("1.2M views") == 1_200_000
    assert parse_view_count("980K views") == 980_000
    assert looks_like_video_id("dQw4w9WgXcQ")
    assert not looks_like_video_id("d0b210a9e94")
