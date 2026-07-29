"""
NoRepeat ↔ Songs Library integration

## Env on NoRepeat backend

```
SONGS_LIBRARY_URL=http://127.0.0.1:8100
SONGS_LIBRARY_ENABLED=true
```

## Flow

1. Queue refresh / sync samples `POST /api/sample` for active seeds (composer match).
2. If sample returns too few tracks, optionally call `POST /api/discover` (later / when seeding).
3. Mapped songs (`youtube_video_id`) become ProviderTracks directly; metadata-only songs fall back to YouTube search by title+movie.

## Endless seed queue

Sample unheard hashes → play → history → sample again → discover when pool low.
"""
