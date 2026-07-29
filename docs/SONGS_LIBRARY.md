# Songs Library integration

NoRepeat can use a standalone **Songs Library** catalog as the primary discovery source for queue refill.

## Run the library

```bash
cd songs-library/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8100
```

Browse: http://127.0.0.1:8100/

Optional later seed:

```bash
python -m app.seed_composers
```

## Enable in NoRepeat

In `.env`:

```
SONGS_LIBRARY_URL=http://127.0.0.1:8100
SONGS_LIBRARY_ENABLED=true
```

When enabled, `QueueService` samples the library for active seeds **before** live YouTube search / home fallback. Unmapped catalog songs are resolved via a targeted YouTube search on title + movie + composer.

See [songs-library/INTEGRATION.md](../songs-library/INTEGRATION.md).
