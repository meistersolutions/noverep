from app.services.youtube_resolve import popularity_from_view_count


def test_popularity_from_view_count_scale():
    assert popularity_from_view_count(None) is None
    assert popularity_from_view_count(0) is None
    assert popularity_from_view_count(-5) is None

    assert popularity_from_view_count(1_000) == 33.33
    assert popularity_from_view_count(100_000) == 55.56
    assert popularity_from_view_count(1_000_000) == 66.67
    assert popularity_from_view_count(1_000_000_000) == 100.0
    assert popularity_from_view_count(10_000_000_000) == 100.0


def test_popularity_increases_with_views():
    low = popularity_from_view_count(10_000)
    mid = popularity_from_view_count(1_000_000)
    high = popularity_from_view_count(50_000_000)
    assert low < mid < high
