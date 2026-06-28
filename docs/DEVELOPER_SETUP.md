# Developer Setup Guide

## Prerequisites

- Docker & Docker Compose
- Node.js 20+ (local frontend dev)
- Python 3.11+ (local backend dev)
- PostgreSQL 16 (if not using Docker)

## Docker (Recommended)

```bash
git clone <repo>
cd noverep
cp .env.example .env
docker compose up --build
```

## Local Backend

1. Start PostgreSQL and Redis:
   ```bash
   docker compose up db redis -d
   ```

2. Create virtual environment:
   ```bash
   cd backend
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   ```

3. Set environment:
   ```bash
   set DATABASE_URL=postgresql+asyncpg://noverep:noverep_secret@localhost:5432/noverep
   set SECRET_KEY=dev-secret-key
   ```

4. Run:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

Tables are auto-created on startup.

## Local Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to `localhost:8000`.

## Running Tests

```bash
cd backend && pytest -v
cd frontend && npm test
```

## API Documentation

Open http://localhost:8000/docs for interactive Swagger UI.

## Google OAuth Setup

1. Create OAuth credentials in Google Cloud Console
2. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`
3. Use `POST /api/v1/auth/google` with Google ID token

## Troubleshooting

| Issue | Solution |
|-------|----------|
| YouTube search fails | Ensure ffmpeg installed in backend container |
| DB connection refused | Wait for postgres healthcheck, verify DATABASE_URL |
| CORS errors | Add frontend origin to CORS_ORIGINS |
