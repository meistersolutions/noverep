from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Songs Library"
    # Local default SQLite; on Render/Neon set DATABASE_URL to Postgres.
    database_url: str = "sqlite:///./data/library.db"
    user_agent: str = (
        "SongsLibrary/0.1 (https://github.com/meistersolutions/noverep; songs-library)"
    )
    wikidata_sparql_url: str = "https://query.wikidata.org/sparql"
    wikidata_api_url: str = "https://www.wikidata.org/w/api.php"
    # 0 = unlimited Wikipedia list ingest for sync discover.
    discover_limit_per_seed: int = 0
    discover_wikidata_limit: int = 500
    discover_musicbrainz_limit: int = 2000
    discover_films_per_tick: int = 25
    enrich_batch_size: int = 15
    enrich_idle_seconds: float = 20.0
    enrich_pause_seconds: float = 2.0
    youtube_resolve_limit: int = 20
    youtube_resolve_batch_size: int = 10
    youtube_resolve_idle_seconds: float = 30.0
    youtube_resolve_pause_seconds: float = 5.0
    # Extra sleep after YouTube 403/bot blocks (multiplied by consecutive failures).
    youtube_resolve_403_cooldown_seconds: float = 120.0
    # Prefer official Data API search on Render (yt-dlp often gets 403 there).
    youtube_api_key: str = ""
    youtube_cookies: str = ""
    youtube_cookies_b64: str = ""
    youtube_cookies_file: str = ""
    cors_origins: str = "*"
    port: int = 8100


settings = Settings()
