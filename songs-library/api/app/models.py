import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


class Song(Base):
    __tablename__ = "songs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    song_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    movie_name: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    composer_name: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    singers: Mapped[list] = mapped_column(JSON, default=list)
    lyricists: Mapped[list] = mapped_column(JSON, default=list)
    popularity: Mapped[float] = mapped_column(Float, default=50.0)
    moods: Mapped[list] = mapped_column(JSON, default=list)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    wikidata_id: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    musicbrainz_id: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    youtube_video_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    wikipedia_title: Mapped[str | None] = mapped_column(String(512), nullable=True)

    playability: Mapped[str] = mapped_column(String(32), default="metadata_only")
    discovered_via: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seed_query: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DiscoverJob(Base):
    __tablename__ = "discover_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    seed: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    phase: Mapped[str] = mapped_column(String(64), default="queued")
    entity_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entity_label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    found: Mapped[int] = mapped_column(Integer, default=0)
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    pages_done: Mapped[int] = mapped_column(Integer, default=0)
    cursor_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
