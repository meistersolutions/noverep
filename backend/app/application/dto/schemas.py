from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    username: str
    is_guest: bool


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str | None = None
    password: str = Field(min_length=6)


class LoginRequest(BaseModel):
    username: str
    password: str


class GoogleAuthRequest(BaseModel):
    id_token: str


class TrackResponse(BaseModel):
    provider: str
    provider_track_id: str
    title: str
    artist: str
    album: str | None
    duration_seconds: int | None
    thumbnail_url: str | None
    canonical_song_id: UUID | None = None
    score: float | None = None
    content_kind: str = "song"


class AudioStreamResponse(BaseModel):
    provider: str
    provider_track_id: str
    url: str
    title: str
    artist: str
    duration_seconds: int | None = None
    thumbnail_url: str | None = None
    mime_type: str | None = None
    http_headers: dict[str, str] | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[TrackResponse]
    total: int


class QueueItemResponse(BaseModel):
    id: UUID
    provider: str
    provider_track_id: str
    title: str
    artist: str
    album: str | None
    thumbnail_url: str | None
    duration_seconds: int | None
    position: int
    is_current: bool
    canonical_song_id: UUID | None = None


class SongDetailsResponse(BaseModel):
    title: str
    artist: str
    album: str | None = None
    song_name: str | None = None
    composed_by: list[str] = Field(default_factory=list)
    lyricist_by: list[str] = Field(default_factory=list)
    performed_by: list[str] = Field(default_factory=list)
    movie_name: str | None = None
    release_year: int | None = None
    musicbrainz_id: str | None = None
    canonical_song_id: UUID | None = None


class LyricsLineResponse(BaseModel):
    time_ms: int
    text: str


class LyricsResponse(BaseModel):
    synced: bool
    plain: str | None = None
    lines: list[LyricsLineResponse] = Field(default_factory=list)
    instrumental: bool = False
    source: str = "lrclib"


class AddToQueueRequest(BaseModel):
    provider: str = "youtube"
    provider_track_id: str
    explicitly_requested: bool = False
    play_now: bool = False
    audio_only: bool = False


class RemoveQueueItemRequest(BaseModel):
    session_id: UUID
    duration_listened: int = 0
    completion_pct: float = 0.0


class RemoveQueueItemResponse(BaseModel):
    was_current: bool
    next_item: QueueItemResponse | None
    queue: list[QueueItemResponse]


class PlayEventRequest(BaseModel):
    provider: str
    provider_track_id: str
    title: str
    artist: str
    album: str | None = None
    genre: str | None = None
    duration_listened: int = 0
    completion_pct: float = 0.0
    skipped: bool = False
    session_id: UUID
    device_id: str | None = None
    explicitly_requested: bool = False


class HistoryEntryResponse(BaseModel):
    id: UUID
    title: str
    artist: str
    album: str | None
    genre: str | None
    provider: str
    provider_track_id: str | None = None
    played_at: datetime
    duration_listened: int
    completion_pct: float
    skipped: bool


class UserPreferencesResponse(BaseModel):
    memory_window: str
    repeat_disabled: bool
    autoplay: bool
    shuffle: bool
    theme: str
    language_preference: str | None
    preferred_languages: list[str] = []
    active_search_query: str | None = None
    active_search_queries: list[str] = []
    favorite_artists: list[str]
    onboarding_completed: bool
    preferred_genres: list[str]
    blocked_artists: list[str]
    blocked_songs: list[str]
    blocked_albums: list[str]
    recommendation_weights: dict
    crossfade_enabled: bool
    gapless_enabled: bool
    discovery_year_from: int | None = None
    discovery_year_to: int | None = None
    discovery_youtube_enabled: bool = True
    playback_mode: str = "discovery"
    active_playlist_id: UUID | None = None


class PlaylistTrackResponse(BaseModel):
    id: UUID
    provider: str
    provider_track_id: str
    title: str
    artist: str
    album: str | None
    thumbnail_url: str | None
    duration_seconds: int | None
    position: int


class PlaylistDetailResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_public: bool
    is_system: bool = False
    system_key: str | None = None
    created_at: datetime
    track_count: int
    tracks: list[PlaylistTrackResponse]


class LikedStatusResponse(BaseModel):
    liked: bool
    playlist_id: UUID


class AddPlaylistTrackRequest(BaseModel):
    provider: str = "youtube"
    provider_track_id: str
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    thumbnail_url: str | None = None
    duration_seconds: int | None = None


class UpdatePreferencesRequest(BaseModel):
    memory_window: str | None = None
    repeat_disabled: bool | None = None
    autoplay: bool | None = None
    shuffle: bool | None = None
    theme: str | None = None
    language_preference: str | None = None
    preferred_languages: list[str] | None = None
    active_search_query: str | None = None
    active_search_queries: list[str] | None = None
    favorite_artists: list[str] | None = None
    onboarding_completed: bool | None = None
    preferred_genres: list[str] | None = None
    blocked_artists: list[str] | None = None
    blocked_songs: list[str] | None = None
    blocked_albums: list[str] | None = None
    recommendation_weights: dict | None = None
    crossfade_enabled: bool | None = None
    gapless_enabled: bool | None = None
    discovery_year_from: int | None = Field(default=None, ge=1950, le=2100)
    discovery_year_to: int | None = Field(default=None, ge=1950, le=2100)
    discovery_youtube_enabled: bool | None = None


class PlaylistResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_public: bool
    is_system: bool = False
    system_key: str | None = None
    created_at: datetime


class CreatePlaylistRequest(BaseModel):
    name: str
    description: str | None = None
    is_public: bool = False


class OnboardingRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=50)
    favorite_artists: list[str] = Field(min_length=1, max_length=5)
    language_preference: str | None = Field(
        default=None,
        pattern="^(tamil|english|hindi|telugu|malayalam|kannada|punjabi|all|both|ta|en)$",
    )
    preferred_languages: list[str] = Field(default_factory=list, max_length=7)


class HomeSectionResponse(BaseModel):
    title: str
    tracks: list[TrackResponse]


class HomeRecommendationsResponse(BaseModel):
    sections: list[HomeSectionResponse]


class FeedbackRequest(BaseModel):
    feedback_type: str = Field(pattern="^(bug|feature)$")
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=10, max_length=5000)
    contact_email: str | None = None


class FeedbackResponse(BaseModel):
    id: UUID
    feedback_type: str
    title: str
    status: str
    created_at: datetime
    admin_response: str | None = None
    responded_at: datetime | None = None


class StatisticsResponse(BaseModel):
    songs_played: int
    artists_explored: int
    genres_explored: int
    albums_explored: int
    listening_streak_days: int
    repeat_avoidance_count: int
    discovery_score: int
    most_explored_genres: list[dict]
    top_artists: list[dict]
    listening_by_hour: list[int]
    listening_heatmap: dict[str, int]
