"""Unit tests for YouTube audio stream URL picking."""

from app.infrastructure.providers.youtube.provider import (
    _is_playable_media_url,
    _pick_audio_stream,
)


def test_rejects_storyboard_urls():
    assert not _is_playable_media_url(
        "https://i.ytimg.com/sb/dQw4w9WgXcQ/storyboard3_L0/default.jpg?sqp=x"
    )
    assert not _is_playable_media_url("https://i.ytimg.com/vi/abc/hqdefault.jpg")
    assert _is_playable_media_url(
        "https://rr1---sn-abc.googlevideo.com/videoplayback?expire=1&mime=audio%2Fmp4"
    )


def test_pick_audio_skips_storyboard_top_level_url():
    info = {
        "url": "https://i.ytimg.com/sb/x/storyboard3_L0/default.jpg",
        "formats": [
            {
                "url": "https://i.ytimg.com/sb/x/storyboard3_L0/default.jpg",
                "acodec": "none",
                "vcodec": "none",
            },
            {
                "url": "https://rr1---sn-abc.googlevideo.com/videoplayback?mime=audio",
                "acodec": "mp4a.40.2",
                "vcodec": "none",
                "abr": 128,
                "ext": "m4a",
                "http_headers": {"User-Agent": "test-agent"},
            },
            {
                "url": "https://rr1---sn-abc.googlevideo.com/videoplayback?mime=video",
                "acodec": "mp4a.40.2",
                "vcodec": "avc1",
                "tbr": 800,
                "ext": "mp4",
            },
        ],
    }
    url, headers, mime = _pick_audio_stream(info)
    assert "googlevideo.com" in url
    assert "mime=audio" in url
    assert headers.get("User-Agent") == "test-agent"
    assert mime == "m4a"


def test_pick_audio_raises_when_only_storyboards():
    info = {
        "url": "https://i.ytimg.com/sb/x/storyboard3_L0/default.jpg",
        "formats": [
            {
                "url": "https://i.ytimg.com/sb/x/storyboard3_L0/default.jpg",
                "acodec": "none",
                "vcodec": "none",
            }
        ],
    }
    try:
        _pick_audio_stream(info)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "No playable audio" in str(e)
