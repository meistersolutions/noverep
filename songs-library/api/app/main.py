from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import init_db
from app.routers.api import router as api_router
from app.services.worker import start_background_workers, stop_background_workers

_here = Path(__file__).resolve()
WEB_DIR = next(
    (p for p in (_here.parents[1] / "web", _here.parents[2] / "web") if p.exists()),
    _here.parents[1] / "web",
)

app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.cors_origins == "*" else [
        o.strip() for o in settings.cors_origins.split(",") if o.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.get("/health")
def root_health():
    return {"status": "ok", "service": "songs-library"}


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    start_background_workers()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    stop_background_workers()


if WEB_DIR.exists():
    assets = WEB_DIR / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    def index():
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/composers")
    def composers_page():
        return FileResponse(WEB_DIR / "composers.html")
