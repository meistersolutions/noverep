from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class CanonicalSong:
    """Provider-independent song identity."""

    id: UUID | None
    title: str
    artist: str
    album: str | None
    duration_seconds: int | None
    genre: str | None = None
    language: str | None = None
    release_year: int | None = None
    isrc: str | None = None
    musicbrainz_id: str | None = None
    fingerprint_hash: str | None = None
    popularity: float = 0.0


@dataclass
class ProviderTrack:
    """Track as returned by a music provider."""

    provider: str
    provider_track_id: str
    title: str
    artist: str
    album: str | None
    duration_seconds: int | None
    thumbnail_url: str | None
    stream_url: str | None = None
    canonical_song_id: UUID | None = None
    genre: str | None = None
    language: str | None = None
    release_year: int | None = None
    isrc: str | None = None
    popularity: float = 0.0


@dataclass
class PlayHistoryEntry:
    song_id: UUID
    provider: str
    artist: str
    album: str | None
    genre: str | None
    played_at: datetime
    duration_listened: int
    completion_pct: float
    skipped: bool
    session_id: UUID
    device_id: str | None


@dataclass
class RecommendationWeights:
    artist_diversity: float = 1.0
    genre_diversity: float = 1.0
    album_diversity: float = 0.8
    language_diversity: float = 0.6
    year_diversity: float = 0.5
    popularity: float = 0.7
    freshness: float = 0.9
    randomness: float = 0.4
    time_of_day: float = 0.3
    history_penalty: float = 1.2
    session_length: float = 0.2


@dataclass
class ScoredCandidate:
    track: ProviderTrack
    score: float
    reasons: dict[str, float] = field(default_factory=dict)
