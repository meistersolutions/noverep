from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def _normalize_database_url(url: str) -> str:
    """Accept Neon/Render postgresql:// URLs for sync SQLAlchemy."""
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql+asyncpg://")
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://") and "+psycopg" not in url and "+psycopg2" not in url:
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


DATABASE_URL = _normalize_database_url(settings.database_url)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401
    from sqlalchemy import text

    if DATABASE_URL.startswith("sqlite:///"):
        db_path = DATABASE_URL.removeprefix("sqlite:///")
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)

    # Additive migrations for existing Neon/Postgres deploys.
    alters = [
        "ALTER TABLE discover_jobs ADD COLUMN IF NOT EXISTS phase VARCHAR(64) DEFAULT 'queued'",
        "ALTER TABLE discover_jobs ADD COLUMN IF NOT EXISTS updated INTEGER DEFAULT 0",
        "ALTER TABLE discover_jobs ADD COLUMN IF NOT EXISTS pages_done INTEGER DEFAULT 0",
        "ALTER TABLE discover_jobs ADD COLUMN IF NOT EXISTS cursor_json JSON",
        "ALTER TABLE discover_jobs ADD COLUMN IF NOT EXISTS message TEXT",
    ]
    if DATABASE_URL.startswith("sqlite"):
        # SQLite lacks IF NOT EXISTS for columns in older versions — ignore failures.
        alters = [
            "ALTER TABLE discover_jobs ADD COLUMN phase VARCHAR(64) DEFAULT 'queued'",
            "ALTER TABLE discover_jobs ADD COLUMN updated INTEGER DEFAULT 0",
            "ALTER TABLE discover_jobs ADD COLUMN pages_done INTEGER DEFAULT 0",
            "ALTER TABLE discover_jobs ADD COLUMN cursor_json JSON",
            "ALTER TABLE discover_jobs ADD COLUMN message TEXT",
        ]
    with engine.begin() as conn:
        for stmt in alters:
            try:
                conn.execute(text(stmt))
            except Exception:  # noqa: BLE001
                pass
