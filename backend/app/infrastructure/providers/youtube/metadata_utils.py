"""YouTube title helpers — detect yt-dlp placeholders and fetch real names."""

import json
import re
from urllib.error import URLError
from urllib.request import urlopen

_PLACEHOLDER = re.compile(r"^youtube video\s#?[a-zA-Z0-9_-]+\s*$", re.IGNORECASE)


def is_placeholder_youtube_title(title: str | None) -> bool:
    if not title or not title.strip():
        return True
    t = title.strip()
    if _PLACEHOLDER.match(t):
        return True
    if t.lower().startswith("youtube video"):
        return True
    return False


def pick_display_title(primary: str | None, fallback: str | None) -> str:
    if primary and not is_placeholder_youtube_title(primary):
        return primary.strip()
    if fallback and fallback.strip() and not is_placeholder_youtube_title(fallback):
        return fallback.strip()
    return (primary or fallback or "Unknown").strip()


def pick_display_artist(primary: str | None, fallback: str | None) -> str:
    if primary and primary.strip() and primary.strip().lower() not in ("unknown", "unknown artist"):
        return primary.strip()
    if fallback and fallback.strip():
        return fallback.strip()
    return (primary or fallback or "Unknown Artist").strip()


def fetch_oembed_metadata(video_id: str) -> tuple[str, str] | None:
    """Public YouTube oEmbed — works when yt-dlp returns placeholder titles on cloud hosts."""
    try:
        watch = f"https://www.youtube.com/watch?v={video_id}"
        url = f"https://www.youtube.com/oembed?url={watch}&format=json"
        with urlopen(url, timeout=12) as resp:
            data = json.loads(resp.read().decode())
        title = (data.get("title") or "").strip()
        author = (data.get("author_name") or "").strip()
        if title and not is_placeholder_youtube_title(title):
            return title, author or "Unknown Artist"
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    return None
