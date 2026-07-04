import pytest

from app.application.services.lyrics_service import parse_lrc


class TestLyricsParser:
    def test_parse_synced_lrc(self):
        lrc = "[00:17.12] First line\n[00:20.50] Second line"
        lines = parse_lrc(lrc)
        assert len(lines) == 2
        assert lines[0].text == "First line"
        assert lines[0].time_ms == 17120
        assert lines[1].time_ms == 20500

    def test_parse_plain_fallback(self):
        lrc = "Line one\nLine two"
        lines = parse_lrc(lrc)
        assert len(lines) == 2
        assert lines[0].text == "Line one"
