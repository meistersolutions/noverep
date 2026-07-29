from pydantic_settings import BaseSettings, SettingsConfigDict

# Capacitor WebView origins (Android https scheme, legacy capacitor://, dev http).
CAPACITOR_ORIGINS: tuple[str, ...] = (
    "capacitor://localhost",
    "https://localhost",
    "http://localhost",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "NoRepeat"
    debug: bool = False
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://noverep:noverep_secret@localhost:5432/noverep"
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    # Short-lived access JWT; clients renew via refresh token.
    jwt_access_expire_minutes: int = 60
    jwt_refresh_expire_days: int = 365
    # Deprecated alias kept for existing env files.
    jwt_expire_minutes: int = 60 * 24 * 7

    cors_origins: str = (
        "http://localhost:5173,http://localhost:3000,"
        "capacitor://localhost,https://localhost,http://localhost"
    )

    google_client_id: str = ""
    google_client_secret: str = ""

    youtube_api_key: str = ""
    # Netscape cookies.txt contents (or path) so yt-dlp can bypass YouTube bot checks on datacenter IPs.
    youtube_cookies: str = ""
    youtube_cookies_b64: str = ""
    youtube_cookies_file: str = ""
    spotify_client_id: str = ""
    spotify_client_secret: str = ""

    musicbrainz_user_agent: str = "NoRepeat/1.0 ( https://noverep.onrender.com )"
    musicbrainz_enabled: bool = True
    lrclib_enabled: bool = True

    rate_limit: str = "100/minute"

    admin_username: str = "admin"
    admin_password: str = ""  # set via ADMIN_PASSWORD env; empty = password set later

    # Standalone Songs Library (catalog-backed discovery)
    songs_library_url: str = ""
    songs_library_enabled: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        for origin in CAPACITOR_ORIGINS:
            if origin not in origins:
                origins.append(origin)
        return origins


settings = Settings()
