# Songs Library

Standalone song catalog (API + browse UI) that grows via Wikipedia/Wikidata discovery and feeds NoRepeat.

## Fields

| Field | Description |
|-------|-------------|
| song_name | Title |
| movie_name | Film / OST |
| release_year | Year |
| composer_name | e.g. Ilaiyaraaja |
| singers | List |
| lyricists | List |
| popularity | 1–100 |
| moods | Extensible tags (mirrored from semantic mood tags) |
| content_hash | Dedupe fingerprint |
| youtube_video_id | Playback mapping (optional) |

### Semantic enrichment (local)

| Store | Description |
|-------|-------------|
| `song_enrichments` | Lyrics, summary, controlled tags, vocal/energy/tempo, role hints |
| `song_embeddings` | Embedding vectors in SQLite (cosine search in-process) |

Natural-language search: `POST /api/search` with `{ "q": "sad duet from the 90s" }`.

Configure an OpenAI-compatible LLM + embeddings endpoint (local Ollama recommended):

```powershell
# songs-library/.env (next to docker-compose.yml)
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=llama3.2
EMBEDDING_MODEL=nomic-embed-text
SEMANTIC_ENRICH_ENABLED=true
```

Then `ollama pull llama3.2` and `ollama pull nomic-embed-text`, rebuild/restart the container, and use **Enrich 20** on the home page (or wait for the background worker).

## Quick start (Python)

```bash
cd songs-library/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8100
```

Open http://127.0.0.1:8100/

## Quick start (Docker — recommended on your laptop)

Uses SQLite under `songs-library/data/` (no Neon). Requires Docker Desktop.

**Easiest on Windows** — from `songs-library/`:

```powershell
.\start.cmd          # or: .\start.ps1
# Open UI: http://127.0.0.1:8100/

.\stop.cmd           # or: .\stop.ps1  (keeps data in .\data)
.\status.cmd         # optional: container status
.\logs.cmd           # optional: follow logs
```

Or call Docker Compose directly:

```powershell
cd C:\Users\smile\Projects\noverep\songs-library

# Build image + start (background)
docker compose up -d --build

# Open UI
start http://127.0.0.1:8100/
```

### Start / stop / status

```powershell
cd C:\Users\smile\Projects\noverep\songs-library

# Scripts (preferred on Windows)
.\start.ps1
.\stop.ps1
.\status.ps1
.\logs.ps1

# Or Docker Compose directly
docker compose up -d --build
docker compose down          # keeps data in .\data
docker compose stop
docker compose start
docker compose logs -f
docker compose ps
```

### Export image (save / move to another machine)

```powershell
cd C:\Users\smile\Projects\noverep\songs-library
docker compose build
docker save songs-library:local -o songs-library-local.tar

# On the other machine:
docker load -i songs-library-local.tar
docker run -d --name songs-library -p 8100:8100 -v ${PWD}/data:/app/data -e DATABASE_URL=sqlite:////app/data/library.db songs-library:local
```

Point local NoRepeat API at it:

```
SONGS_LIBRARY_URL=http://127.0.0.1:8100
SONGS_LIBRARY_ENABLED=true
```

Seed later (optional):

```bash
python -m app.seed_composers
# or
curl -X POST http://127.0.0.1:8100/api/discover \
  -H 'Content-Type: application/json' \
  -d '{"seeds":["Ilaiyaraaja","A. R. Rahman","Yuvan Shankar Raja"]}'
```

## API

- `GET /api/health` — health
- `GET /api/stats` — counts by composer
- `GET /api/composers` — composer names with movie/album and song counts
- Web UI `/composers` — composer names with song counts
- `GET /api/songs` — list/filter (`tag=` for enrichment tags)
- `GET /api/songs/{id}/enrichment` — tags, summary, status
- `POST /api/songs` — manual add
- `PATCH /api/songs/{id}` — update
- `POST /api/search` — natural-language search over local embeddings
- `POST /api/enrich` — queue (and opportunistically run) semantic enrichment
- `GET /api/enrich/semantic/status` — enrichment / vector counts
- `POST /api/discover` — Wikidata discovery for seeds
- `POST /api/discover/jobs/{id}/end` — end a running/pending seed and archive it (hides from home list)
- `POST /api/discover/jobs/{id}/restart` — re-queue a stuck seed (resume film crawl, or `?reset=true` from scratch)
- `GET /api/discover/jobs` — list discover jobs (archived hidden by default)
- `POST /api/sample` — unheard batch for NoRepeat queue (`tags` + `moods`)
- `POST /api/resolve/youtube` — resolve YouTube ids for unmapped songs
  (uses `YOUTUBE_API_KEY` when set; yt-dlp fallback often 403s on Render)
- `POST /api/playlists/export` — export mapped songs as a YouTube playlist payload

## NoRepeat

Set on the NoRepeat backend (Render env):

```
SONGS_LIBRARY_URL=https://songs-library.onrender.com
SONGS_LIBRARY_ENABLED=true
```

## Deploy to the internet (Render + Neon)

Same pattern as NoRepeat — see [docs/DEPLOY_SONGS_LIBRARY.md](../docs/DEPLOY_SONGS_LIBRARY.md).
