from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Songs Library"
    database_url: str = f"sqlite:///{ROOT / 'data' / 'library.db'}"
    user_agent: str = "SongsLibrary/0.1 (NoRepeat companion)"
    wikidata_sparql_url: str = "https://query.wikidata.org/sparql"
    wikidata_api_url: str = "https://www.wikidata.org/w/api.php"
    discover_limit_per_seed: int = 250
    youtube_resolve_limit: int = 20
    cors_origins: str = "*"


settings = Settings()
