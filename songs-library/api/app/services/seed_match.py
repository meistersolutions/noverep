"""Match a free-text seed against any relevant song credit / title field."""

from __future__ import annotations

from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Query, Session

from app.models import Song


def seed_match_filters(seed: str):
    """SQLAlchemy OR clauses: seed may be composer, singer, director, film, etc."""
    text = (seed or "").strip()
    if not text:
        return []
    like = f"%{text}%"
    return [
        Song.composer_name.ilike(like),
        Song.movie_name.ilike(like),
        Song.song_name.ilike(like),
        Song.seed_query.ilike(like),
        Song.wikipedia_title.ilike(like),
        cast(Song.singers, String).ilike(like),
        cast(Song.lyricists, String).ilike(like),
        cast(Song.directors, String).ilike(like),
        cast(Song.actors, String).ilike(like),
        cast(Song.actresses, String).ilike(like),
    ]


def apply_seed_match(query: Query, seed: str | None) -> Query:
    clauses = seed_match_filters(seed or "")
    if not clauses:
        return query
    return query.filter(or_(*clauses))


def count_songs_for_seed(db: Session, seed: str) -> int:
    q = apply_seed_match(db.query(Song), seed)
    return int(q.count() or 0)
