import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False)
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    preferences: Mapped["UserPreferencesModel"] = relationship(back_populates="user", uselist=False)
    sessions: Mapped[list["SessionModel"]] = relationship(back_populates="user")


class ArtistModel(Base):
    __tablename__ = "artists"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    normalized_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AlbumModel(Base):
    __tablename__ = "albums"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    artist_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("artists.id"), nullable=True)
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GenreModel(Base):
    __tablename__ = "genres"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)


class ProviderModel(Base):
    __tablename__ = "providers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SongModel(Base):
    """Canonical cross-provider song entity."""

    __tablename__ = "songs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    artist_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("artists.id"), nullable=True)
    album_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("albums.id"), nullable=True)
    genre_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("genres.id"), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    isrc: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    musicbrainz_id: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    fingerprint_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    normalization_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)
    popularity: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    provider_mappings: Mapped[list["ProviderMappingModel"]] = relationship(back_populates="song")
    history_entries: Mapped[list["ListeningHistoryModel"]] = relationship(back_populates="song")

    __table_args__ = (
        Index("ix_songs_artist_title", "normalized_title"),
    )


class ProviderMappingModel(Base):
    __tablename__ = "provider_mappings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    song_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("songs.id"), nullable=False)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id"), nullable=False)
    provider_track_id: Mapped[str] = mapped_column(String(255), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    song: Mapped[SongModel] = relationship(back_populates="provider_mappings")
    provider: Mapped[ProviderModel] = relationship()

    __table_args__ = (
        UniqueConstraint("provider_id", "provider_track_id", name="uq_provider_track"),
        Index("ix_provider_mappings_song", "song_id"),
    )


class ListeningHistoryModel(Base):
    __tablename__ = "listening_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    song_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("songs.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    artist_name: Mapped[str] = mapped_column(String(512), nullable=False)
    album_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    genre_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    duration_listened: Mapped[int] = mapped_column(Integer, default=0)
    completion_pct: Mapped[float] = mapped_column(Float, default=0.0)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    explicitly_requested: Mapped[bool] = mapped_column(Boolean, default=False)

    song: Mapped[SongModel] = relationship(back_populates="history_entries")
    session: Mapped["SessionModel"] = relationship(back_populates="history")

    __table_args__ = (
        Index("ix_history_user_played", "user_id", "played_at"),
        Index("ix_history_user_song", "user_id", "song_id"),
        Index("ix_history_session", "session_id"),
    )


class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[UserModel] = relationship(back_populates="sessions")
    history: Mapped[list[ListeningHistoryModel]] = relationship(back_populates="session")


class QueueItemModel(Base):
    __tablename__ = "queue_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    song_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("songs.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_track_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    artist: Mapped[str] = mapped_column(String(512), nullable=False)
    album: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_queue_user_position", "user_id", "position"),
    )


class PlaylistModel(Base):
    __tablename__ = "playlists"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    system_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PlaylistItemModel(Base):
    __tablename__ = "playlist_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    playlist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("playlists.id"), nullable=False)
    song_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("songs.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserPreferencesModel(Base):
    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    memory_window: Mapped[str] = mapped_column(String(20), default="30d")
    repeat_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    autoplay: Mapped[bool] = mapped_column(Boolean, default=True)
    shuffle: Mapped[bool] = mapped_column(Boolean, default=False)
    theme: Mapped[str] = mapped_column(String(20), default="dark")
    language_preference: Mapped[str | None] = mapped_column(String(20), nullable=True)
    preferred_languages: Mapped[list | None] = mapped_column(JSONB, default=list)
    active_search_query: Mapped[str | None] = mapped_column(String(255), nullable=True)
    favorite_artists: Mapped[list | None] = mapped_column(JSONB, default=list)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    preferred_genres: Mapped[list | None] = mapped_column(JSONB, default=list)
    blocked_artists: Mapped[list | None] = mapped_column(JSONB, default=list)
    blocked_songs: Mapped[list | None] = mapped_column(JSONB, default=list)
    blocked_albums: Mapped[list | None] = mapped_column(JSONB, default=list)
    recommendation_weights: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    crossfade_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    gapless_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    discovery_year_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discovery_year_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    playback_mode: Mapped[str] = mapped_column(String(20), default="discovery")
    active_playlist_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("playlists.id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[UserModel] = relationship(back_populates="preferences")


class RecommendationCacheModel(Base):
    __tablename__ = "recommendation_cache"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    cache_key: Mapped[str] = mapped_column(String(255), nullable=False)
    candidates: Mapped[dict] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "cache_key", name="uq_rec_cache_user_key"),
        Index("ix_rec_cache_expires", "expires_at"),
    )


class FeedbackModel(Base):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    feedback_type: Mapped[str] = mapped_column(String(20), nullable=False)  # bug | feature
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_feedback_created", "created_at"),)
