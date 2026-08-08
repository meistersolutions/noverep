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
    # Classified Wikipedia BFS budgets (0 pages = unlimited).
    discover_max_pages: int = 2500
    discover_max_depth: int = 4
    discover_queue_batch_commit: int = 5
    enrich_batch_size: int = 15
    # Idle sleeps are intentionally long — continuous workers were the main Neon
    # egress driver on the Free 5 GB/month transfer cap.
    enrich_idle_seconds: float = 300.0
    enrich_pause_seconds: float = 5.0
    # Semantic enrich: lyrics + LLM tags/summary + local embeddings.
    # Requires an OpenAI-compatible endpoint (Ollama or cloud).
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "llama3.2"
    embedding_model: str = "nomic-embed-text"
    semantic_enrich_enabled: bool = True
    semantic_enrich_batch_size: int = 5
    semantic_enrich_idle_seconds: float = 60.0
    semantic_enrich_pause_seconds: float = 3.0
    lyrics_max_chars: int = 8000
    embed_lyrics_chars: int = 1500
    youtube_resolve_limit: int = 20
    youtube_resolve_batch_size: int = 10
    youtube_resolve_idle_seconds: float = 300.0
    youtube_resolve_pause_seconds: float = 15.0
    # Extra sleep after YouTube 403/bot blocks (multiplied by consecutive failures).
    youtube_resolve_403_cooldown_seconds: float = 120.0
    discover_queue_idle_seconds: float = 5.0
    # Set BACKGROUND_WORKERS_ENABLED=false on Render to stop all DB loops
    # (use when Neon transfer is exhausted / recovering).
    background_workers_enabled: bool = True
    # Prefer official Data API search on Render (yt-dlp often gets 403 there).
    youtube_api_key: str = ""
    youtube_cookies: str = ""
    youtube_cookies_b64: str = ""
    youtube_cookies_file: str = ""
    # Optional: ping NoRepeat so mutual keepalive keeps both free-tier services awake
    # once either one is woken by a user request. Long interval reduces wake churn.
    noverep_keepalive_url: str = ""
    noverep_keepalive_seconds: float = 300.0
    cors_origins: str = "*"
    port: int = 8100


settings = Settings()
