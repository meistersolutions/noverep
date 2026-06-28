# NoRepeat Architecture

## System Overview

```mermaid
flowchart TB
    subgraph Presentation
        UI[React Frontend]
        API[FastAPI REST API]
    end

    subgraph Application
        QS[Queue Service]
        RE[Recommendation Engine]
        MS[Memory Service]
        SN[Song Normalizer]
        SS[Statistics Service]
        AS[Auth Service]
    end

    subgraph Domain
        MP[MusicProvider Interface]
        CE[Canonical Song Entity]
    end

    subgraph Infrastructure
        PG[(PostgreSQL)]
        RD[(Redis)]
        YT[YouTube Provider]
        SP[Spotify Provider]
    end

    UI --> API
    API --> QS & RE & MS & SS & AS
    RE --> MS & SN & MP
    QS --> RE & MS
    SN --> PG
    MS --> PG
    MP --> YT & SP
    API --> PG
    API --> RD
```

## Recommendation Pipeline

```mermaid
sequenceDiagram
    participant U as User
    participant API as FastAPI
    participant RE as Recommendation Engine
    participant MS as Memory Service
    participant YT as YouTube Provider
    participant DB as PostgreSQL

    U->>API: GET /search?q=rock
    API->>RE: recommend(user_id, query)
    RE->>YT: search(query)
    YT-->>RE: ProviderTrack[]
    RE->>DB: resolve canonical songs
    RE->>MS: get_blocked_song_ids()
    MS->>DB: query listening_history
    MS-->>RE: blocked UUIDs
    RE->>RE: score & sort & randomize
    RE-->>API: ScoredCandidate[]
    API-->>U: filtered results
```

## Entity Relationship Diagram

```mermaid
erDiagram
    USERS ||--o| USER_PREFERENCES : has
    USERS ||--o{ LISTENING_HISTORY : generates
    USERS ||--o{ QUEUE_ITEMS : owns
    USERS ||--o{ PLAYLISTS : creates
    USERS ||--o{ SESSIONS : starts

    SONGS ||--o{ PROVIDER_MAPPINGS : maps
    SONGS ||--o{ LISTENING_HISTORY : tracked
    SONGS }o--|| ARTISTS : by
    SONGS }o--o| ALBUMS : on
    SONGS }o--o| GENRES : tagged

    PROVIDERS ||--o{ PROVIDER_MAPPINGS : provides

    PLAYLISTS ||--o{ PLAYLIST_ITEMS : contains
    PLAYLIST_ITEMS }o--|| SONGS : references
```

## Cross-Provider Song Normalization

```mermaid
flowchart LR
    YT[YouTube Video] --> N[Song Normalizer]
    SP[Spotify Track] --> N
    AM[Apple Music Track] --> N
    LO[Local File] --> N
    N --> CK[normalization_key]
    CK --> CS[Canonical Song]
    CS --> PM[Provider Mappings]
```

Normalization key: `SHA256(normalize(artist) | normalize(title) | duration_bucket)`

Future: ISRC, MusicBrainz ID, audio fingerprint hash.

## Memory Window Logic

```mermaid
flowchart TD
    A[User requests song] --> B{Explicitly requested?}
    B -->|Yes| Z[Allow play]
    B -->|No| C{Repeat disabled?}
    C -->|Yes| Z
    C -->|No| D{In memory window?}
    D -->|Yes| X[Block / find alternative]
    D -->|No| Z
```

## Clean Architecture Layers

| Layer          | Responsibility                          | Examples                          |
|----------------|-----------------------------------------|-----------------------------------|
| Presentation   | HTTP, routing, DTOs                     | `routes.py`, Pydantic schemas     |
| Application    | Use cases, orchestration                | `QueueService`, `RecommendationEngine` |
| Domain         | Business rules, interfaces              | `MusicProvider`, `CanonicalSong`  |
| Infrastructure | External systems                        | PostgreSQL, yt-dlp, JWT             |

## Scoring Formula

```
Score =
  artist_diversity_bonus/penalty +
  genre_diversity_bonus/penalty +
  album_diversity_penalty +
  language_diversity_penalty +
  year_diversity_penalty +
  popularity × weight +
  freshness × weight +
  time_of_day × weight +
  random(0, randomness_weight)
```

All weights configurable per user via `user_preferences.recommendation_weights`.

## Deployment

```mermaid
flowchart LR
    subgraph Docker Compose
        FE[frontend:5173]
        BE[backend:8000]
        DB[postgres:5432]
        RD[redis:6379]
    end
    FE --> BE
    BE --> DB
    BE --> RD
```

## Extension Points

1. **New Provider** – Implement `MusicProvider` interface, register in `dependencies.py`
2. **ML Recommendations** – Replace `RecommendationEngine._score_track` with model inference
3. **Fingerprinting** – Populate `SongModel.fingerprint_hash`, match before normalization key
4. **Background Jobs** – Add Celery/ARQ worker for cache warming, MusicBrainz enrichment
