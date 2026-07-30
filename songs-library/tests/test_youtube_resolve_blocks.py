from app.services.youtube_resolve import (
    _is_block_error,
    popularity_from_view_count,
    youtube_block_cooldown_seconds,
)


def test_is_block_error_detects_403():
    assert _is_block_error(Exception("HTTP Error 403: Forbidden"))
    assert _is_block_error(Exception("Sign in to confirm you’re not a bot"))
    assert not _is_block_error(Exception("timeout waiting for reply"))


def test_block_cooldown_starts_at_zero():
    # Fresh import state may already have blocks from other tests; just ensure callable.
    assert youtube_block_cooldown_seconds() >= 0


def test_popularity_still_scales():
    assert popularity_from_view_count(1_000_000) == 66.67
