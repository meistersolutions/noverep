"""Controlled vocabulary for song semantic enrichment."""

from __future__ import annotations

MOOD_TAGS: frozenset[str] = frozenset(
    {
        "sad",
        "happy",
        "romantic",
        "melancholic",
        "angry",
        "peaceful",
        "nostalgic",
        "devotional",
        "playful",
    }
)

ENERGY_FEEL_TAGS: frozenset[str] = frozenset(
    {"upbeat", "calm", "intense", "dreamy"}
)

VOCAL_TAGS: frozenset[str] = frozenset(
    {"solo", "duet", "group", "chorus_heavy", "instrumental"}
)

ROLE_TAGS: frozenset[str] = frozenset(
    {"introduction", "ending", "interval", "title_track"}
)

THEME_TAGS: frozenset[str] = frozenset(
    {
        "rain",
        "party",
        "wedding",
        "heartbreak",
        "friendship",
        "patriotism",
        "item_number",
    }
)

ALL_TAGS: frozenset[str] = (
    MOOD_TAGS | ENERGY_FEEL_TAGS | VOCAL_TAGS | ROLE_TAGS | THEME_TAGS
)

VOCAL_VALUES: frozenset[str] = frozenset(
    {"solo", "duet", "group", "instrumental", "unknown"}
)
ENERGY_VALUES: frozenset[str] = frozenset({"low", "medium", "high"})
TEMPO_VALUES: frozenset[str] = frozenset({"slow", "mid", "fast"})
ROLE_HINT_VALUES: frozenset[str] = frozenset(
    {"introduction", "ending", "interval", "title_track", "montage"}
)


def normalize_tag(raw: str) -> str | None:
    tag = (raw or "").strip().casefold().replace(" ", "_").replace("-", "_")
    if tag in ALL_TAGS:
        return tag
    return None


def filter_allowed_tags(raw_tags: list | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_tags or []:
        tag = normalize_tag(str(item))
        if tag and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def moods_from_tags(tags: list[str]) -> list[str]:
    return [t for t in tags if t in MOOD_TAGS]


def normalize_vocal(raw: str | None) -> str:
    v = (raw or "unknown").strip().casefold()
    return v if v in VOCAL_VALUES else "unknown"


def normalize_energy(raw: str | None) -> str:
    v = (raw or "medium").strip().casefold()
    return v if v in ENERGY_VALUES else "medium"


def normalize_tempo(raw: str | None) -> str:
    v = (raw or "mid").strip().casefold()
    return v if v in TEMPO_VALUES else "mid"


def filter_role_hints(raw: list | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in raw or []:
        hint = (str(item) or "").strip().casefold().replace(" ", "_").replace("-", "_")
        if hint in ROLE_HINT_VALUES and hint not in seen:
            seen.add(hint)
            out.append(hint)
    return out
