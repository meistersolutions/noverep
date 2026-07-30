# NoRepeat ↔ Songs Library integration

## Env on NoRepeat backend

```
SONGS_LIBRARY_URL=http://127.0.0.1:8100
SONGS_LIBRARY_ENABLED=true
```

## Flow

1. Queue refresh / sync samples `POST /api/sample` for active seeds (composer match), preferring `only_mapped=true`.
2. When the unheard pool drops below 30 tracks, NoRepeat queues `POST /api/discover` (continuous background ingest).
3. Every library track enters the NoRepeat queue **only after** it has a `youtube_video_id`. Mapped songs enqueue immediately; unmapped songs are batch-resolved via `POST /api/songs/{id}/resolve-youtube` (parallel, capped concurrency) before enqueue. Returns **404** if the song id is unknown, **422** if YouTube lookup failed. Songs that fail resolve are **skipped** (never left with an empty video id).
4. Background workers in Songs Library continuously enrich metadata, resolve YouTube ids, and crawl Wikipedia/Wikidata.

## Endless seed queue

```
Sample unheard (exclude_hashes from history) → play → history → sample again → discover when pool low
```

## Playlist export (P4 foundation)

`POST /api/playlists/export` returns mapped `youtube_video_id`s and a `youtube_watch_url` for manual or future OAuth playlist creation.
