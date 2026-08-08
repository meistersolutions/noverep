"""Build embed documents and run cosine search over local song_embeddings."""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Song, SongEmbedding, SongEnrichment
from app.services.llm_client import embed_text
from app.services.tags import filter_allowed_tags


def build_embed_text(
    song: Song,
    *,
    summary: str | None,
    tags: list[str],
    vocal: str,
    energy: str,
    lyrics: str | None,
) -> str:
    singers = ", ".join(song.singers or []) if song.singers else ""
    lyricists = ", ".join(song.lyricists or []) if song.lyricists else ""
    year = f" ({song.release_year})" if song.release_year else ""
    movie = f"{song.movie_name or ''}{year}".strip()
    tag_line = ", ".join(tags) if tags else ""
    lyrics_snip = (lyrics or "").strip()
    max_lyrics = settings.embed_lyrics_chars
    if len(lyrics_snip) > max_lyrics:
        lyrics_snip = lyrics_snip[:max_lyrics]
    parts = [
        f"title: {song.song_name}",
        f"movie: {movie}" if movie else "",
        f"language: {song.language}" if song.language else "",
        f"composer: {song.composer_name}" if song.composer_name else "",
        f"singers: {singers}" if singers else "",
        f"lyricists: {lyricists}" if lyricists else "",
        f"vocal: {vocal} | energy: {energy} | tags: {tag_line}",
        f"summary: {summary}" if summary else "",
        f"lyrics: {lyrics_snip}" if lyrics_snip else "",
    ]
    return "\n".join(p for p in parts if p)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def search_songs(
    db: Session,
    *,
    query_embedding: list[float],
    limit: int = 20,
    language: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    tags: list[str] | None = None,
) -> list[tuple[Song, SongEnrichment | None, float]]:
    allowed_tags = filter_allowed_tags(tags)
    rows = (
        db.query(Song, SongEmbedding, SongEnrichment)
        .join(SongEmbedding, SongEmbedding.song_id == Song.id)
        .outerjoin(SongEnrichment, SongEnrichment.song_id == Song.id)
        .all()
    )
    scored: list[tuple[Song, SongEnrichment | None, float]] = []
    for song, emb_row, enrichment in rows:
        if language and (song.language or "").casefold() != language.casefold():
            # soft: also allow substring
            if language.casefold() not in (song.language or "").casefold():
                continue
        if year_from is not None and song.release_year is not None and song.release_year < year_from:
            continue
        if year_to is not None and song.release_year is not None and song.release_year > year_to:
            continue
        if allowed_tags:
            song_tags = set((enrichment.tags if enrichment else None) or song.moods or [])
            if not all(t in song_tags for t in allowed_tags):
                continue
        vector = emb_row.embedding or []
        score = cosine_similarity(query_embedding, vector)
        scored.append((song, enrichment, score))
    scored.sort(key=lambda item: item[2], reverse=True)
    return scored[:limit]


async def embed_query(q: str) -> list[float]:
    return await embed_text(q.strip())
