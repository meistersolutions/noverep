from app.services.worker import _is_stopped


def test_is_stopped_statuses():
    assert _is_stopped("archived")
    assert _is_stopped("cancelled")
    assert _is_stopped("ARCHIVED")
    assert not _is_stopped("running")
    assert not _is_stopped("pending")
    assert not _is_stopped("completed")
    assert not _is_stopped(None)
