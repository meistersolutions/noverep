from app.application.services.song_matcher import (
    extract_core_title,
    is_same_song,
    title_similarity,
)


class TestSongMatcher:
    def test_extract_core_title_strips_noise(self):
        core = extract_core_title(
            "Nila Kaikiradhu (Official Video) - A. R. Rahman",
            "Golden Voice Of Hariharan",
        )
        assert "nila" in core.lower()

    def test_same_song_different_youtube_titles(self):
        assert is_same_song(
            "Nila Kaikiradhu-Indira-A. R. Rahman",
            "Golden Voice Of Hariharan",
            256,
            "Nila Kaikiradhu | Indira | Tamil Song",
            "A R Rahman",
            258,
        )

    def test_same_song_official_video_variant(self):
        assert is_same_song(
            "Bohemian Rhapsody (Official Video)",
            "Queen",
            354,
            "Bohemian Rhapsody - Queen",
            "Queen Official",
            355,
        )

    def test_different_songs_not_matched(self):
        assert not is_same_song(
            "Shape of You",
            "Ed Sheeran",
            233,
            "Perfect",
            "Ed Sheeran",
            263,
        )

    def test_title_similarity_partial_overlap_not_enough(self):
        score = title_similarity("Summer Nights", "Grease", "Winter Nights", "Grease")
        assert score < 0.82
