import pytest

from app.application.services.lyrics_service import (
    lyrics_item_score,
    parse_lrc,
    pick_best_lyrics_item,
)


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


class TestLyricsMatching:
    def test_rejects_kanne_kalaimane_for_kalaimane(self):
        wrong = {
            "trackName": "Kanne Kalaimane",
            "artistName": "K. J. Yesudas",
            "albumName": "Moondram Pirai",
            "duration": 300,
        }
        score = lyrics_item_score(wrong, "Kalaimane", "Hariharan", 298, "Thalam")
        assert score < 0.82

    def test_pick_best_lyrics_item_prefers_correct_match(self):
        items = [
            {
                "trackName": "Kanne Kalaimane",
                "artistName": "K. J. Yesudas",
                "albumName": "Moondram Pirai",
                "duration": 300,
                "syncedLyrics": "[00:10.00] wrong",
            },
            {
                "trackName": "Kalaimane",
                "artistName": "Hariharan",
                "albumName": "Thalam",
                "duration": 298,
                "syncedLyrics": "[00:10.00] right",
            },
        ]
        picked = pick_best_lyrics_item(items, "Kalaimane", "Hariharan", 298, "Thalam")
        assert picked is not None
        assert picked["trackName"] == "Kalaimane"

    def test_pick_best_lyrics_item_returns_none_for_only_wrong_match(self):
        items = [
            {
                "trackName": "Kanne Kalaimane",
                "artistName": "K. J. Yesudas",
                "albumName": "Moondram Pirai",
                "duration": 300,
            },
        ]
        assert pick_best_lyrics_item(items, "Kalaimane", "Hariharan", 298, "Thalam") is None
