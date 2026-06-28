"""Tests for YouTube metadata title helpers."""

from app.infrastructure.providers.youtube.metadata_utils import (
    is_placeholder_youtube_title,
    pick_display_artist,
    pick_display_title,
)


def test_is_placeholder_youtube_title():
    assert is_placeholder_youtube_title("youtube video #6o8pxa1PJ1g")
    assert is_placeholder_youtube_title("YouTube video 6o8pxa1PJ1g")
    assert is_placeholder_youtube_title("")
    assert not is_placeholder_youtube_title("Bohemian Rhapsody")


def test_pick_display_title_prefers_real_over_placeholder():
    assert pick_display_title("youtube video #abc", "Real Song Name") == "Real Song Name"
    assert pick_display_title("Real Song Name", "Other") == "Real Song Name"


def test_pick_display_artist_prefers_known():
    assert pick_display_artist("Unknown Artist", "Queen") == "Queen"
    assert pick_display_artist("Queen", "Other") == "Queen"
