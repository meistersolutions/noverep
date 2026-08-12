"""Lyrics + LLM tag/summary enrichment and local embedding upsert."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Song, SongEmbedding, SongEnrichment
from app.services import llm_client
from app.services.lyrics_fetch import fetch_lyrics_for_song
from app.services.tags import (
    ALL_TAGS,
    filter_allowed_tags,
    filter_role_hints,
    moods_from_tags,
    normalize_energy,
    normalize_tempo,
    normalize_vocal,
)
from app.services.vector_search import build_embed_text


def _commit(db: Session) -> None:
    from app.services.db_lock import sqlite_write

    with sqlite_write():
        db.commit()


CLASSIFY_SYSTEM = f"""You classify film/soundtrack songs for a music catalog.
Return ONLY a JSON object with keys:
- summary: 1-2 sentences describing mood and theme
- tags: array of tags chosen ONLY from this allow-list: {sorted(ALL_TAGS)}
- vocal: one of solo, duet, group, instrumental, unknown
- energy: one of low, medium, high
- tempo_feel: one of slow, mid, fast
- role_hints: array from introduction, ending, interval, title_track, montage (may be empty)

Omit uncertain tags. Do not invent tags outside the allow-list.
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_pending_row(db: Session, song_id: str) -> SongEnrichment:
    row = db.query(SongEnrichment).filter(SongEnrichment.song_id == song_id).one_or_none()
    if row:
        return row
    row = SongEnrichment(song_id=song_id, status="pending")
    db.add(row)
    db.flush()
    return row


def enqueue_songs(
    db: Session,
    *,
    song_ids: list[str] | None = None,
    limit: int = 50,
    force: bool = False,
) -> dict:
    if song_ids:
        songs = db.query(Song).filter(Song.id.in_(song_ids)).all()
    else:
        # Prefer mapped songs that lack enrichment or are still pending.
        existing = {
            r.song_id
            for r in db.query(SongEnrichment.song_id, SongEnrichment.status).all()
        }
        q = db.query(Song).order_by(
            (Song.playability != "mapped"),
            Song.updated_at.desc(),
        )
        songs = []
        for song in q.limit(limit * 5):
            if song.id not in existing or force:
                songs.append(song)
            if len(songs) >= limit:
                break
    queued = 0
    for song in songs:
        row = ensure_pending_row(db, song.id)
        if force or row.status in {"pending", "failed", "lyrics_missing"}:
            row.status = "pending"
            row.error = None
            queued += 1
    _commit(db)
    return {"queued": queued, "requested": len(songs)}


def songs_needing_semantic_enrich(db: Session, *, limit: int = 5) -> list[Song]:
    pending_ids = [
        r.song_id
        for r in db.query(SongEnrichment.song_id)
        .filter(SongEnrichment.status == "pending")
        .limit(limit)
        .all()
    ]
    if pending_ids:
        return db.query(Song).filter(Song.id.in_(pending_ids)).all()

    enriched_ids = {r.song_id for r in db.query(SongEnrichment.song_id).all()}
    q = db.query(Song)
    if enriched_ids:
        q = q.filter(~Song.id.in_(enriched_ids))
    return list(
        q.order_by((Song.playability != "mapped"), Song.updated_at.desc())
        .limit(limit)
        .all()
    )


def semantic_status(db: Session) -> dict:
    total = db.query(func.count(Song.id)).scalar() or 0
    by_status = dict(
        db.query(SongEnrichment.status, func.count(SongEnrichment.song_id))
        .group_by(SongEnrichment.status)
        .all()
    )
    embeddings = db.query(func.count(SongEmbedding.song_id)).scalar() or 0
    return {
        "total_songs": total,
        "embeddings": embeddings,
        "by_status": by_status,
        "pending": int(by_status.get("pending") or 0),
        "ready": int(by_status.get("ready") or 0),
        "lyrics_missing": int(by_status.get("lyrics_missing") or 0),
        "failed": int(by_status.get("failed") or 0),
        "llm_configured": llm_client.llm_configured(),
        "semantic_enrich_enabled": bool(settings.semantic_enrich_enabled),
    }


async def enrich_one_song(db: Session, song: Song) -> SongEnrichment:
    row = ensure_pending_row(db, song.id)
    if not llm_client.llm_configured():
        row.status = "failed"
        row.error = "LLM_BASE_URL is not configured"
        _commit(db)
        db.refresh(row)
        return row

    lyrics_text = None
    lyrics_source = None
    try:
        lyrics = await fetch_lyrics_for_song(song)
        if lyrics:
            lyrics_source = lyrics.source
            if lyrics.instrumental:
                lyrics_text = ""
            else:
                lyrics_text = lyrics.text
    except Exception as exc:  # noqa: BLE001
        row.error = f"lyrics_fetch: {exc}"

    singers = ", ".join(song.singers or [])
    user_prompt = (
        f"Song: {song.song_name}\n"
        f"Movie/album: {song.movie_name or ''}\n"
        f"Year: {song.release_year or ''}\n"
        f"Language: {song.language or ''}\n"
        f"Composer: {song.composer_name or ''}\n"
        f"Singers: {singers}\n"
        f"Lyricists: {', '.join(song.lyricists or [])}\n"
    )
    if lyrics_text:
        user_prompt += f"\nLyrics:\n{lyrics_text[: settings.lyrics_max_chars]}\n"
    else:
        user_prompt += "\nLyrics: (unavailable — classify from metadata only)\n"

    try:
        raw = await llm_client.chat_json(CLASSIFY_SYSTEM, user_prompt)
    except Exception as exc:  # noqa: BLE001
        row.status = "failed"
        row.error = f"llm: {exc}"
        row.lyrics_text = lyrics_text
        row.lyrics_source = lyrics_source
        _commit(db)
        db.refresh(row)
        return row

    tags = filter_allowed_tags(raw.get("tags") if isinstance(raw.get("tags"), list) else [])
    vocal = normalize_vocal(str(raw.get("vocal") or ""))
    energy = normalize_energy(str(raw.get("energy") or ""))
    tempo = normalize_tempo(str(raw.get("tempo_feel") or ""))
    role_hints = filter_role_hints(
        raw.get("role_hints") if isinstance(raw.get("role_hints"), list) else []
    )
    summary = str(raw.get("summary") or "").strip() or None
    if summary and len(summary) > 800:
        summary = summary[:800]

    embed_doc = build_embed_text(
        song,
        summary=summary,
        tags=tags,
        vocal=vocal,
        energy=energy,
        lyrics=lyrics_text,
    )
    model_tag = f"{settings.llm_model}+{settings.embedding_model}"

    try:
        vector = await llm_client.embed_text(embed_doc)
    except Exception as exc:  # noqa: BLE001
        row.status = "failed"
        row.error = f"embed: {exc}"
        row.summary = summary
        row.tags = tags
        row.vocal = vocal
        row.energy = energy
        row.tempo_feel = tempo
        row.role_hints = role_hints
        row.lyrics_text = lyrics_text
        row.lyrics_source = lyrics_source
        row.embed_text = embed_doc
        row.model_tag = model_tag
        _commit(db)
        db.refresh(row)
        return row

    row.lyrics_text = lyrics_text
    row.lyrics_source = lyrics_source
    row.summary = summary
    row.tags = tags
    row.tag_scores = None
    row.vocal = vocal
    row.energy = energy
    row.tempo_feel = tempo
    row.role_hints = role_hints
    row.embed_text = embed_doc
    row.model_tag = model_tag
    row.error = None
    row.enriched_at = _utcnow()
    # Embeddings are written either way; lyrics_missing marks weaker metadata-only runs.
    row.status = "ready" if lyrics_text is not None else "lyrics_missing"

    song.moods = moods_from_tags(tags)

    emb = db.query(SongEmbedding).filter(SongEmbedding.song_id == song.id).one_or_none()
    if emb is None:
        emb = SongEmbedding(
            song_id=song.id,
            embedding=vector,
            dims=len(vector),
            model=settings.embedding_model,
        )
        db.add(emb)
    else:
        emb.embedding = vector
        emb.dims = len(vector)
        emb.model = settings.embedding_model

    _commit(db)
    db.refresh(row)
    return row


async def enrich_batch(db: Session, *, limit: int | None = None) -> dict:
    if not settings.semantic_enrich_enabled:
        return {"checked": 0, "enriched": 0, "failed": 0, "skipped": True}
    if not llm_client.llm_configured():
        return {"checked": 0, "enriched": 0, "failed": 0, "llm_configured": False}
    batch = limit or settings.semantic_enrich_batch_size
    songs = songs_needing_semantic_enrich(db, limit=batch)
    enriched = 0
    failed = 0
    for song in songs:
        row = await enrich_one_song(db, song)
        if row.status in {"ready", "lyrics_missing"} and not row.error:
            enriched += 1
        elif row.status == "failed":
            failed += 1
        elif row.status in {"ready", "lyrics_missing"}:
            enriched += 1
    return {"checked": len(songs), "enriched": enriched, "failed": failed}
