# AGENTS.md

## Cursor Cloud specific instructions

NoRepeat is a music-discovery web app. For local dev it runs as three pieces:

- PostgreSQL 16 (required datastore)
- `backend/` — FastAPI API on port 8000 (`uvicorn app.main:app --reload`)
- `frontend/` — React + Vite dev server on port 5173 (`npm run dev`)

Redis is listed in `requirements.txt`/`docker-compose.yml` but is **not** imported anywhere in the backend, so it is not needed to run or test the app locally.

### Startup (services are NOT auto-started by the update script)

- PostgreSQL: start with `sudo pg_ctlcluster 16 main start`. The `noverep` role (password `noverep_secret`) and `noverep` database are created during initial setup; a fresh VM snapshot preserves them. If the DB/role is missing, recreate with:
  `sudo -u postgres psql -c "CREATE ROLE noverep LOGIN PASSWORD 'noverep_secret' CREATEDB;"` and `sudo -u postgres psql -c "CREATE DATABASE noverep OWNER noverep;"`.
- Backend: `cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000`. The venv lives at `backend/.venv`. Config is read from `backend/.env` (gitignored; see values below). On startup the app runs `Base.metadata.create_all` + idempotent `ALTER TABLE`s and seeds an `admin` user, so **no migration step is needed** — the DB schema is created/updated automatically on every boot.
- Frontend: `cd frontend && npm run dev`. Vite proxies `/api` → `http://localhost:8000` (see `frontend/vite.config.ts`), so no API URL env var is needed for local dev.

`backend/.env` (create if missing) needs at minimum:
```
DATABASE_URL=postgresql+asyncpg://noverep:noverep_secret@localhost:5432/noverep
SECRET_KEY=dev-local-secret-key-change-me
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin1234
```

### Lint / test / build

- Backend lint: `cd backend && . .venv/bin/activate && ruff check .` (ruff config is in `pyproject.toml`; `ruff` is a dev-only tool, install with `pip install ruff` if absent). The repo currently has many pre-existing ruff findings.
- Backend tests: `cd backend && . .venv/bin/activate && pytest`. Note: `tests/integration/test_api.py::test_guest_auth` passes in isolation but fails during a full-suite run due to a pre-existing cross-test asyncpg event-loop teardown quirk (the endpoint itself works). All other tests pass.
- Frontend tests: `cd frontend && npm test` (vitest). `src/lib/api.test.ts` has a pre-existing broken import (`./lib/api` should be `./api`) and fails; `src/lib/yearValidation.test.ts` passes.
- Frontend lint: `npm run lint` is defined but **ESLint is not actually a dependency and there is no eslint config**, so it does not work out of the box. Do not rely on it.
- Frontend build: `cd frontend && npm run build` (vite build).

### Gotchas

- `passlib` logs a trapped `error reading bcrypt version` / `module 'bcrypt' has no attribute '__about__'` warning on startup. It is harmless — password hashing still works.
- Search/playback uses `yt-dlp` to hit YouTube directly (no API key required). This works from the cloud VM. If YouTube starts blocking the datacenter IP, set `YOUTUBE_COOKIES*` in `.env` (see `.env.example`).
- The `songs-library/` service is an optional standalone catalog (port 8100) and is disabled by default (`SONGS_LIBRARY_ENABLED=false`); it is not required to run or demo the main app.
