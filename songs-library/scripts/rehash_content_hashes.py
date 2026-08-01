"""CLI wrapper: regenerate songs.content_hash against DATABASE_URL.

Prefer the live endpoint when only Render has the Songs Library DB:

  curl -X POST https://songs-library.onrender.com/api/maintenance/rehash-content-hashes
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "songs-library" / "api"
sys.path.insert(0, str(API))


def _load_env() -> None:
    for path in (ROOT / ".env", API / ".env", Path.cwd() / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip("'").strip('"'))


def main() -> int:
    _load_env()
    url = os.environ.get("SONGS_LIBRARY_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        print("No DATABASE_URL / SONGS_LIBRARY_DATABASE_URL", file=sys.stderr)
        return 1
    os.environ["DATABASE_URL"] = url
    parsed = urlparse(
        url.replace("postgresql+asyncpg://", "postgresql://").replace(
            "postgresql+psycopg://", "postgresql://"
        )
    )
    print(f"host={parsed.hostname} db={(parsed.path or '').lstrip('/').split('?')[0]}")

    from app.db import SessionLocal
    from app.services.rehash import rehash_all_songs

    db = SessionLocal()
    try:
        result = rehash_all_songs(db)
        for k, v in result.items():
            print(f"{k}={v}")
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
