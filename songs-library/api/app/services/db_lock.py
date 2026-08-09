"""Serialize SQLite writers (Docker Desktop bind mounts often break concurrent locks)."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from collections.abc import Iterator

from app.db import DATABASE_URL

_write_lock = threading.RLock()


def using_sqlite() -> bool:
    return DATABASE_URL.startswith("sqlite")


@contextmanager
def sqlite_write() -> Iterator[None]:
    """Hold while committing SQLite changes from any worker thread."""
    if using_sqlite():
        with _write_lock:
            yield
    else:
        yield
