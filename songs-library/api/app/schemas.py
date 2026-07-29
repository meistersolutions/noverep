from datetime import datetime

from pydantic import BaseModel, Field


class SongCreate(BaseModel):
    song_name: str
    movie_name: str | None = None
    release_year: int | None = None
    composer_name: str | None = None
    singers: list[str] = Field(default_factory=list)
    lyricists: list[str] = Field(default_factory=list)
    popularity: float = Field(default=50.0, ge=0, le=100)
    moods: list[str] = Field(default_factory=list)
    wikidata_id: str | None = None
    musicbrainz_id: str | None = None
    youtube_video_id: str | None = None
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
    popularity: float | None = Field(default=None, ge=0, le=100)
    moods: list[str] | None = None
    youtube_video_id: str | None = None
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
    popularity: float
    moods: list[str]
    content_hash: str
    wikidata_id: str | None
    musicbrainz_id: str | None
    youtube_video_id: str | None
    wikipedia_title: str | None
    playability: str
    discovered_via: str | None
    seed_query: str | None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class DiscoverRequest(BaseModel):
    seeds: list[str]
    limit_per_seed: int | None = None


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
    cursor_json: dict | None = None

    model_config = {"from_attributes": True}


class EnrichStatusOut(BaseModel):
    missing_singers: int
    missing_lyricists: int
    missing_either: int
    last_batch: dict | None = None


class SampleRequest(BaseModel):
    composer: str | None = None
    seed: str | None = None
    moods: list[str] = Field(default_factory=list)
    year_from: int | None = None
    year_to: int | None = None
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
