"""Content hash compatible with the Songs Library service."""

from __future__ import annotations

import hashlib
import re
import unicodedata


def _norm(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().strip()
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def library_content_hash(
    song_name: str,
    movie_name: str | None = None,
    composer_name: str | None = None,
    release_year: int | None = None,
    language: str | None = None,
) -> str:
    """Dedupe fingerprint: song + movie only (matches Songs Library)."""
    del composer_name, release_year, language
    payload = "|".join([_norm(song_name), _norm(movie_name)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
