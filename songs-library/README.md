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
- `GET /api/songs` — list/filter
- `POST /api/songs` — manual add
- `PATCH /api/songs/{id}` — update
- `POST /api/discover` — Wikidata discovery for seeds
- `POST /api/sample` — unheard batch for NoRepeat queue
- `POST /api/resolve/youtube` — resolve YouTube ids for unmapped songs

## NoRepeat

Set `SONGS_LIBRARY_URL=http://127.0.0.1:8100` on the NoRepeat backend. Queue refresh samples this library first when configured.
