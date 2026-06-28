import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text

from app.config import settings
from app.infrastructure.database.models import Base
from app.infrastructure.database.session import engine
from app.presentation.api.v1.routes import router

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger()

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit])


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "ALTER TABLE user_preferences "
                "ADD COLUMN IF NOT EXISTS favorite_artists JSONB DEFAULT '[]'"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE user_preferences "
                "ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN DEFAULT FALSE"
            )
        )
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name VARCHAR(100)")
        )
        await conn.execute(
            text(
                "ALTER TABLE user_preferences "
                "ADD COLUMN IF NOT EXISTS discovery_year_from INTEGER"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE user_preferences "
                "ADD COLUMN IF NOT EXISTS discovery_year_to INTEGER"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE user_preferences "
                "ADD COLUMN IF NOT EXISTS preferred_languages JSONB DEFAULT '[]'"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE user_preferences "
                "ADD COLUMN IF NOT EXISTS active_search_query VARCHAR(255)"
            )
        )
        await conn.execute(
            text("ALTER TABLE playlists ADD COLUMN IF NOT EXISTS is_system BOOLEAN DEFAULT FALSE")
        )
        await conn.execute(
            text("ALTER TABLE playlists ADD COLUMN IF NOT EXISTS system_key VARCHAR(50)")
        )
        await conn.execute(
            text(
                "ALTER TABLE user_preferences "
                "ADD COLUMN IF NOT EXISTS active_playlist_id UUID REFERENCES playlists(id)"
            )
        )
        # Seed providers
        await conn.execute(
            text(
                "INSERT INTO providers (id, name, display_name, is_active) "
                "VALUES (gen_random_uuid(), 'youtube', 'YouTube', true), "
                "(gen_random_uuid(), 'spotify', 'Spotify', false) "
                "ON CONFLICT (name) DO NOTHING"
            )
        )
    logger.info("startup_complete")
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description="Never-repeat intelligent music discovery platform",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/")
async def root():
    return {
        "app": settings.app_name,
        "message": "This is the NoRepeat API. Open the web app URL to play music.",
        "web_app": "https://noverep.onrender.com",
        "health": "/health",
        "api": settings.api_prefix,
        "docs": "/docs",
    }


@app.get("/health")
@limiter.limit("30/minute")
async def health(request: Request):
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {e}"
    return {
        "status": "ok" if db_status == "healthy" else "degraded",
        "database": db_status,
        "version": "1.0.0",
    }


app.include_router(router, prefix=settings.api_prefix)
