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

# Small pool + pre-ping: one Render free dyno talking to Neon. Prefer Neon's
# pooled connection string (*-pooler.*) in DATABASE_URL to cut connection churn.
_engine_kwargs: dict = {"connect_args": connect_args}
if not DATABASE_URL.startswith("sqlite"):
    _engine_kwargs.update(
        {
            "pool_size": 2,
            "max_overflow": 1,
            "pool_pre_ping": True,
            "pool_recycle": 280,
        }
    )

engine = create_engine(DATABASE_URL, **_engine_kwargs)
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
    if DATABASE_URL.startswith("sqlite"):
        alters = [
            "ALTER TABLE discover_jobs ADD COLUMN phase VARCHAR(64) DEFAULT 'queued'",
            "ALTER TABLE discover_jobs ADD COLUMN updated INTEGER DEFAULT 0",
            "ALTER TABLE discover_jobs ADD COLUMN pages_done INTEGER DEFAULT 0",
            "ALTER TABLE discover_jobs ADD COLUMN cursor_json JSON",
            "ALTER TABLE discover_jobs ADD COLUMN message TEXT",
            "ALTER TABLE songs ADD COLUMN language VARCHAR(64)",
            "ALTER TABLE songs ADD COLUMN directors JSON",
            "ALTER TABLE songs ADD COLUMN actors JSON",
            "ALTER TABLE songs ADD COLUMN actresses JSON",
            "ALTER TABLE songs ADD COLUMN youtube_view_count INTEGER",
        ]
    else:
        alters = [
            "ALTER TABLE discover_jobs ADD COLUMN IF NOT EXISTS phase VARCHAR(64) DEFAULT 'queued'",
            "ALTER TABLE discover_jobs ADD COLUMN IF NOT EXISTS updated INTEGER DEFAULT 0",
            "ALTER TABLE discover_jobs ADD COLUMN IF NOT EXISTS pages_done INTEGER DEFAULT 0",
            "ALTER TABLE discover_jobs ADD COLUMN IF NOT EXISTS cursor_json JSON",
            "ALTER TABLE discover_jobs ADD COLUMN IF NOT EXISTS message TEXT",
            "ALTER TABLE songs ADD COLUMN IF NOT EXISTS language VARCHAR(64)",
            "ALTER TABLE songs ADD COLUMN IF NOT EXISTS directors JSON DEFAULT '[]'",
            "ALTER TABLE songs ADD COLUMN IF NOT EXISTS actors JSON DEFAULT '[]'",
            "ALTER TABLE songs ADD COLUMN IF NOT EXISTS actresses JSON DEFAULT '[]'",
            "ALTER TABLE songs ADD COLUMN IF NOT EXISTS youtube_view_count INTEGER",
        ]
    with engine.begin() as conn:
        for stmt in alters:
            try:
                conn.execute(text(stmt))
            except Exception:  # noqa: BLE001
                pass
