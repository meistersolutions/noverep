"""Semantic song matching — same track, different YouTube uploads."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

TITLE_NOISE = re.compile(
    r"\b("
    r"official\s*(music\s*)?video|official\s*audio|lyrics?\s*video|lyric\s*video|"
    r"full\s*video|hd\s*video|4k|8k|remaster(?:ed)?|audio\s*only|"
    r"velvet\s*shorts|shorts|live\s*performance|cover\s*version|"
    r"music\s*video|mv\b|ft\.?|feat\.?|featuring"
    r")\b",
    re.IGNORECASE,
)

PAREN_CONTENT = re.compile(r"\([^)]*\)|\[[^\]]*\]|\{[^}]*\}")

STOP_WORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "from",
        "ft",
        "feat",
        "featuring",
        "vs",
        "song",
        "songs",
        "audio",
        "video",
        "official",
        "lyrics",
        "lyric",
    }
)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_title_noise(title: str) -> str:
    cleaned = PAREN_CONTENT.sub(" ", title)
    return TITLE_NOISE.sub(" ", cleaned)


def extract_core_title(title: str, artist: str | None = None) -> str:
    """Best-effort song name from messy YouTube titles."""
    cleaned = strip_title_noise(title)
    parts = [p.strip() for p in re.split(r"[|\-–—:•]+", cleaned) if p.strip()]
    if not parts:
        return title.strip()

    norm_artist = normalize_text(artist or "")
    meaningful: list[str] = []
    for part in parts:
        norm_part = normalize_text(part)
        if len(norm_part) < 3:
            continue
        if norm_artist and (
            norm_part == norm_artist or norm_artist in norm_part or norm_part in norm_artist
        ):
            continue
        meaningful.append(part)

    if not meaningful:
        meaningful = parts

    # YouTube titles are usually "Song - Artist"; keep the first meaningful segment.
    return meaningful[0]


def token_set(text: str) -> set[str]:
    return {
        token
        for token in normalize_text(text).split()
        if len(token) >= 2 and token not in STOP_WORDS
    }


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    union = len(left | right)
    return intersection / union if union else 0.0


def artist_similarity(artist_a: str, artist_b: str) -> float:
    norm_a = normalize_text(artist_a)
    norm_b = normalize_text(artist_b)
    if not norm_a or not norm_b:
        return 0.0
    if norm_a == norm_b:
        return 1.0
    if norm_a in norm_b or norm_b in norm_a:
        return 0.9
    return jaccard_similarity(token_set(artist_a), token_set(artist_b))


def title_similarity(
    title_a: str,
    title_b: str,
    artist_a: str = "",
    artist_b: str = "",
) -> float:
    core_a = extract_core_title(title_a, artist_a)
    core_b = extract_core_title(title_b, artist_b)
    norm_a = normalize_text(core_a)
    norm_b = normalize_text(core_b)
    if not norm_a or not norm_b:
        return 0.0
    if norm_a == norm_b:
        return 1.0
    if norm_a in norm_b or norm_b in norm_a:
        return 0.92
    sequence = SequenceMatcher(None, norm_a, norm_b).ratio()
    tokens = jaccard_similarity(token_set(core_a), token_set(core_b))
    return max(sequence, tokens)


def duration_compatible(
    duration_a: int | None,
    duration_b: int | None,
    *,
    abs_tolerance: int = 25,
    pct_tolerance: float = 0.08,
) -> bool:
    if duration_a is None or duration_b is None:
        return True
    diff = abs(duration_a - duration_b)
    average = (duration_a + duration_b) / 2
    return diff <= abs_tolerance or (average > 0 and diff / average <= pct_tolerance)


def match_score(
    title_a: str,
    artist_a: str,
    duration_a: int | None,
    title_b: str,
    artist_b: str,
    duration_b: int | None,
) -> float:
    if not duration_compatible(duration_a, duration_b):
        return 0.0
    title_score = title_similarity(title_a, title_b, artist_a, artist_b)
    artist_score = artist_similarity(artist_a, artist_b)
    if title_score >= 0.9:
        return title_score * 0.8 + max(artist_score, 0.35) * 0.2
    return title_score * 0.65 + artist_score * 0.35


def is_same_song(
    title_a: str,
    artist_a: str,
    duration_a: int | None,
    title_b: str,
    artist_b: str,
    duration_b: int | None,
    *,
    threshold: float = 0.82,
) -> bool:
    score = match_score(title_a, artist_a, duration_a, title_b, artist_b, duration_b)
    if score < threshold:
        return False

    title_score = title_similarity(title_a, title_b, artist_a, artist_b)
    artist_score = artist_similarity(artist_a, artist_b)

    if title_score >= 0.88 and duration_compatible(duration_a, duration_b):
        return True
    if title_score >= 0.78 and artist_score >= 0.4:
        return True
    return score >= threshold
