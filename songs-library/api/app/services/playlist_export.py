"""Export library selections as YouTube playlist payloads (P4 foundation).

OAuth-based playlist creation on YouTube is out of scope; this returns a
structured list ready for manual import or a future YouTube Data API worker.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Song
from app.schemas import PlaylistExportItem, PlaylistExportRequest, PlaylistExportResponse


def export_playlist(db: Session, body: PlaylistExportRequest) -> PlaylistExportResponse:
    query = db.query(Song)

    if body.song_ids:
        query = query.filter(Song.id.in_(body.song_ids))
    else:
        if body.composer:
            query = query.filter(Song.composer_name.ilike(f"%{body.composer}%"))
        if body.movie:
            query = query.filter(Song.movie_name.ilike(f"%{body.movie}%"))
        if body.mood:
            query = query.filter(Song.moods.contains([body.mood]))
        if body.year_from is not None:
            query = query.filter(Song.release_year >= body.year_from)
        if body.year_to is not None:
            query = query.filter(Song.release_year <= body.year_to)

    if body.only_mapped:
        query = query.filter(Song.youtube_video_id.isnot(None))

    songs = (
        query.order_by(Song.popularity.desc(), Song.release_year.desc(), Song.song_name)
        .limit(body.limit)
        .all()
    )

    items: list[PlaylistExportItem] = []
    for song in songs:
        if not song.youtube_video_id:
            continue
        items.append(
            PlaylistExportItem(
                song_id=song.id,
                song_name=song.song_name,
                movie_name=song.movie_name,
                composer_name=song.composer_name,
                youtube_video_id=song.youtube_video_id,
                youtube_url=f"https://www.youtube.com/watch?v={song.youtube_video_id}",
            )
        )

    video_ids = [item.youtube_video_id for item in items]
    # YouTube supports watch_videos?video_ids= for up to 50 ids in one URL.
    watch_url = None
    if video_ids:
        watch_url = "https://www.youtube.com/watch_videos?video_ids=" + ",".join(video_ids[:50])

    return PlaylistExportResponse(
        title=body.title or "Songs Library export",
        description=body.description,
        item_count=len(items),
        items=items,
        youtube_watch_url=watch_url,
        video_ids=video_ids,
    )
