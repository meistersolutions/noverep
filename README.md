# NoRepeat – Intelligent Music Discovery Platform

> **A song should never repeat until the user explicitly allows it.**

NoRepeat is a production-ready cross-platform music player that maximizes discovery while respecting listening history. Built with FastAPI, PostgreSQL, React, and a modular provider architecture.

## Quick Start

```bash
cp .env.example .env
# Edit .env – set SECRET_KEY at minimum

docker compose up --build
```

| Service  | URL                        |
|----------|----------------------------|
| Frontend | http://localhost:5173      |
| API      | http://localhost:8000      |
| API Docs | http://localhost:8000/docs |
| Health   | http://localhost:8000/health |

## Core Features

- **Never-Repeat Guarantee** – Configurable memory window (1 day → forever)
- **Smart Recommendations** – Weighted scoring for artist/genre/album/language/year diversity
- **Cross-Provider Songs** – Canonical song entity maps YouTube, Spotify, Apple Music, local files
- **Intelligent Queue** – Next track auto-discovered when queue is exhausted
- **YouTube Playback** – Search & play via yt-dlp + YouTube IFrame API
- **JWT Auth** – Guest mode, registration, Google OAuth (optional)
- **Statistics Dashboard** – Discovery score, streaks, heatmaps, top artists/genres

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   React UI  │────▶│  FastAPI API │────▶│   PostgreSQL    │
│  (Vite/TS)  │     │  Services    │     │   + Redis       │
└─────────────┘     └──────┬───────┘     └─────────────────┘
                           │
                    ┌──────▼───────┐
                    │   Providers   │
                    │ YouTube │ Spotify* │
                    └──────────────┘
                    * scaffolded
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed diagrams.

## Project Structure

```
noverep/
├── backend/           # FastAPI application
│   ├── app/
│   │   ├── domain/          # Entities, interfaces, enums
│   │   ├── application/     # Services, DTOs
│   │   ├── infrastructure/  # DB, providers, auth
│   │   └── presentation/    # API routes
│   └── tests/
├── frontend/          # React + Vite + TailwindCSS
├── docker-compose.yml
└── docs/
```

## Local Development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Requires PostgreSQL running (or use `docker compose up db redis`).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Recommendation Pipeline

```
Search → Normalize → Dedupe → Memory Filter → Block Lists → Score → Sort → Randomize → Play
```

Configurable weights in Settings or via `PATCH /api/v1/preferences`.

## Environment Variables

| Variable            | Description                          |
|---------------------|--------------------------------------|
| `SECRET_KEY`        | JWT signing key (required in prod)   |
| `DATABASE_URL`      | PostgreSQL connection string         |
| `GOOGLE_CLIENT_ID`  | Google OAuth client ID               |
| `YOUTUBE_API_KEY`   | Optional YouTube Data API key        |
| `SPOTIFY_CLIENT_ID` | Spotify integration (future)         |

## Testing

```bash
# Backend
cd backend && pytest

# Frontend
cd frontend && npm test
```

## Free cloud hosting (no home PC)

See **[docs/DEPLOY_FREE.md](docs/DEPLOY_FREE.md)** — deploy to **Render + Neon** (free tier) using the included `render.yaml` blueprint.

## API Highlights

| Endpoint              | Description                |
|-----------------------|----------------------------|
| `POST /auth/guest`    | Anonymous session          |
| `GET /search?q=`      | Search with memory filter  |
| `POST /queue/next`    | Intelligent next track     |
| `POST /playback/event`| Record listening history   |
| `GET /statistics`     | Discovery dashboard        |
| `PATCH /preferences`  | Memory window & weights    |

## Future Roadmap

- [ ] Spotify Web API integration
- [ ] Apple Music & Amazon Music providers
- [ ] Audio fingerprinting (AcoustID)
- [ ] MusicBrainz ISRC lookup
- [ ] Collaborative filtering / ML recommendations
- [ ] Offline mode, mobile & desktop apps
- [ ] CarPlay / Android Auto
- [ ] Podcast support

## License

MIT
