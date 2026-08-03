from datetime import datetime

from pydantic import BaseModel, Field


class SongCreate(BaseModel):
    song_name: str
    movie_name: str | None = None
    release_year: int | None = None
    composer_name: str | None = None
    singers: list[str] = Field(default_factory=list)
    lyricists: list[str] = Field(default_factory=list)
    language: str | None = None
    directors: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    actresses: list[str] = Field(default_factory=list)
    popularity: float = Field(default=50.0, ge=0, le=100)
    moods: list[str] = Field(default_factory=list)
    wikidata_id: str | None = None
    musicbrainz_id: str | None = None
    youtube_video_id: str | None = None
    youtube_view_count: int | None = None
    wikipedia_title: str | None = None
    discovered_via: str | None = None
    seed_query: str | None = None
    extra: dict | None = None


class SongUpdate(BaseModel):
    song_name: str | None = None
    movie_name: str | None = None
    release_year: int | None = None
    composer_name: str | None = None
    singers: list[str] | None = None
    lyricists: list[str] | None = None
    language: str | None = None
    directors: list[str] | None = None
    actors: list[str] | None = None
    actresses: list[str] | None = None
    popularity: float | None = Field(default=None, ge=0, le=100)
    moods: list[str] | None = None
    youtube_video_id: str | None = None
    youtube_view_count: int | None = None
    playability: str | None = None
    extra: dict | None = None


class SongOut(BaseModel):
    id: str
    song_name: str
    movie_name: str | None
    release_year: int | None
    composer_name: str | None
    singers: list[str]
    lyricists: list[str]
    language: str | None = None
    directors: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    actresses: list[str] = Field(default_factory=list)
    popularity: float
    moods: list[str]
    content_hash: str
    wikidata_id: str | None
    musicbrainz_id: str | None
    youtube_video_id: str | None
    youtube_view_count: int | None = None
    wikipedia_title: str | None
    playability: str
    discovered_via: str | None
    seed_query: str | None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class DiscoverRequest(BaseModel):
    seeds: list[str]
    limit_per_seed: int | None = None
    force: bool = Field(
        default=False,
        description="Queue discovery even when the catalog already has matching songs.",
    )


class DiscoverSeedResult(BaseModel):
    seed: str
    entity_id: str | None = None
    entity_label: str | None = None
    found: int = 0
    inserted: int = 0
    skipped: int = 0
    updated: int = 0
    error: str | None = None


class DiscoverResponse(BaseModel):
    results: list[DiscoverSeedResult]
    total_inserted: int
    total_skipped: int
    total_updated: int = 0
    job_ids: list[str] = Field(default_factory=list)


class DiscoverJobOut(BaseModel):
    id: str
    seed: str
    status: str
    phase: str
    entity_id: str | None = None
    entity_label: str | None = None
    found: int
    inserted: int
    skipped: int
    updated: int
    pages_done: int
    message: str | None = None
    error: str | None = None
    # Slim progress only — never ship fat cursor queue/seen over the wire (Neon egress).
    film_index: int | None = None
    films_total: int | None = None
    queue_len: int | None = None
    seen_len: int | None = None
    wiki_list_page_count: int = 0
    created_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class DiscoverJobPagesOut(BaseModel):
    """Fetched only when the portal opens job Details — not on every poll."""

    id: str
    wiki_list_pages: list[str] = Field(default_factory=list)
    filmography_pages: list[str] = Field(default_factory=list)
    film_pages: list[str] = Field(default_factory=list)


class EnrichStatusOut(BaseModel):
    missing_singers: int
    missing_lyricists: int
    missing_either: int
    last_batch: dict | None = None


class WorkerStatusOut(BaseModel):
    total_songs: int
    mapped: int
    metadata_only: int
    mapped_pct: float
    youtube_api_configured: bool
    consecutive_blocks: int
    block_cooldown_seconds: float
    last_resolve_batch: dict | None = None
    hint: str = ""


class SampleRequest(BaseModel):
    composer: str | None = None
    seed: str | None = None
    moods: list[str] = Field(default_factory=list)
    languages: list[str] = Field(
        default_factory=list,
        description="Language codes/labels to keep (e.g. tamil, hindi). Empty = any.",
    )
    year_from: int | None = None
    year_to: int | None = None
    popularity_min: float | None = Field(
        default=None, ge=0, le=100, description="Inclusive lower bound on popularity (0–100)."
    )
    popularity_max: float | None = Field(
        default=None, ge=0, le=100, description="Inclusive upper bound on popularity (0–100)."
    )
    exclude_hashes: list[str] = Field(default_factory=list)
    exclude_ids: list[str] = Field(default_factory=list)
    only_mapped: bool = False
    limit: int = Field(default=20, ge=1, le=100)


class ResolveYoutubeRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    composer: str | None = None
    dry_run: bool = False


class ResolveYoutubeResult(BaseModel):
    attempted: int
    resolved: int
    failed: int
    songs: list[SongOut] = Field(default_factory=list)


class StatsOut(BaseModel):
    total_songs: int
    by_composer: dict[str, int]
    mapped: int
    metadata_only: int
    youtube_api_configured: bool = False


class RehashResultOut(BaseModel):
    loaded: int
    hash_values_changed: int
    collision_groups: int
    merged_deleted: int
    remaining: int


class ComposerOut(BaseModel):
    name: str
    song_count: int
    movie_count: int


class PlaylistExportItem(BaseModel):
    song_id: str
    song_name: str
    movie_name: str | None = None
    composer_name: str | None = None
    youtube_video_id: str
    youtube_url: str


class PlaylistExportRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    song_ids: list[str] = Field(default_factory=list)
    composer: str | None = None
    movie: str | None = None
    mood: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    only_mapped: bool = True
    limit: int = Field(default=50, ge=1, le=200)


class PlaylistExportResponse(BaseModel):
    title: str
    description: str | None = None
    item_count: int
    items: list[PlaylistExportItem]
    youtube_watch_url: str | None = None
    video_ids: list[str] = Field(default_factory=list)
