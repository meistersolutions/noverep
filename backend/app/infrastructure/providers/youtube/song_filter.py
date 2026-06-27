"""Filter YouTube results to single-song music tracks only."""

import re

# Titles suggesting compilations, mixes, or multi-song uploads
MULTI_SONG_PATTERN = re.compile(
    r"\b("
    r"non[- ]?stop|nonstop|mashup|medley|compilation|playlist|"
    r"full album|jukebox|continuous|mega mix|party mix|"
    r"mix\s*of|best of|greatest hits|hour mix|hours mix|"
    r"superhit|super hit|all songs|all time|"
    r"dj mix|remix pack|mash\s*up|"
    r"\d+\s*songs|\d+\s*hits"
    r")\b",
    re.IGNORECASE,
)

# Non-music / video content indicators
NON_MUSIC_PATTERN = re.compile(
    r"\b(trailer|teaser|interview|reaction|tutorial|vlog|"
    r"behind the scenes|making of|lyrics video only)\b",
    re.IGNORECASE,
)

MIN_DURATION_SEC = 45
MAX_DURATION_SEC = 600  # 10 min – longer uploads are usually compilations


def normalize_search_query(query: str) -> str:
    """Bias YouTube search toward individual music tracks."""
    q = query.strip()
    if not q:
        return "official audio song"
    lower = q.lower()
    if "official" not in lower and "audio" not in lower and "song" not in lower:
        return f"{q} official audio song"
    return q


def is_single_song_track(title: str, duration_seconds: int | None) -> bool:
    if not title or len(title.strip()) < 2:
        return False

    if NON_MUSIC_PATTERN.search(title):
        return False

    if MULTI_SONG_PATTERN.search(title):
        return False

    if duration_seconds is not None:
        if duration_seconds < MIN_DURATION_SEC:
            return False
        if duration_seconds > MAX_DURATION_SEC:
            return False

    return True


def filter_song_tracks(tracks: list, limit: int) -> list:
    """Filter ProviderTrack list to single songs."""
    result = []
    for track in tracks:
        if is_single_song_track(track.title, track.duration_seconds):
            result.append(track)
        if len(result) >= limit:
            break
    return result
