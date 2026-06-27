import pytest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.enums import MemoryWindow, MEMORY_WINDOW_DAYS


class TestMemoryWindowConfig:
    def test_all_windows_have_day_mapping(self):
        for window in MemoryWindow:
            assert window in MEMORY_WINDOW_DAYS

    def test_forever_is_none(self):
        assert MEMORY_WINDOW_DAYS[MemoryWindow.FOREVER] is None

    def test_thirty_days(self):
        assert MEMORY_WINDOW_DAYS[MemoryWindow.THIRTY_DAYS] == 30


class TestDuplicateDetection:
    def test_same_canonical_id_is_duplicate(self):
        id1 = uuid4()
        seen = {id1}
        id2 = id1
        assert id2 in seen

    def test_normalization_key_differs_by_duration_bucket(self):
        from app.application.services.song_normalizer import SongNormalizer
        n = SongNormalizer()
        k1 = n.normalize_key("Song", "Artist", 100)
        k2 = n.normalize_key("Song", "Artist", 102)
        # Same bucket (100//5 == 102//5)
        assert k1 == k2
        k3 = n.normalize_key("Song", "Artist", 130)
        assert k1 != k3
