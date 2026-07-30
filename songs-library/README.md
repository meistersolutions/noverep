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
| moods | Extensible tags |
| content_hash | Dedupe fingerprint |
| youtube_video_id | Playback mapping (optional) |

## Quick start

```bash
cd songs-library/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8100
```

Open http://127.0.0.1:8100/

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
- Web UI `/composers` — composer names with song counts
- `GET /api/songs` — list/filter
- `POST /api/songs` — manual add
- `PATCH /api/songs/{id}` — update
- `POST /api/discover` — Wikidata discovery for seeds
- `POST /api/discover/jobs/{id}/end` — end a running/pending seed and archive it (hides from home list)
- `POST /api/discover/jobs/{id}/restart` — re-queue a stuck seed (resume film crawl, or `?reset=true` from scratch)
- `GET /api/discover/jobs` — list discover jobs (archived hidden by default)
- `POST /api/sample` — unheard batch for NoRepeat queue
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
