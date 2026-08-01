"""One-shot / API: regenerate songs.content_hash and merge collisions."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from app.models import Song
from app.services.hashing import content_hash


def _pick_keeper(rows: list[Song]) -> Song:
    def score(s: Song) -> tuple:
        return (
            1 if (s.youtube_video_id or "") else 0,
            1 if (s.composer_name or "") else 0,
            len(s.singers or []),
            len(s.lyricists or []),
            1 if (s.language or "") else 0,
            1 if s.release_year else 0,
            1 if (s.wikidata_id or "") else 0,
            1 if (s.musicbrainz_id or "") else 0,
            float(s.popularity or 0),
        )

    return sorted(rows, key=score, reverse=True)[0]


def _merge_fields(keeper: Song, donor: Song) -> None:
    if donor.composer_name and not keeper.composer_name:
        keeper.composer_name = donor.composer_name
    if donor.movie_name and not keeper.movie_name:
        keeper.movie_name = donor.movie_name
    if donor.release_year and not keeper.release_year:
        keeper.release_year = donor.release_year
    if donor.language and not keeper.language:
        keeper.language = donor.language
    if donor.youtube_video_id and not keeper.youtube_video_id:
        keeper.youtube_video_id = donor.youtube_video_id
        keeper.playability = "mapped"
    if donor.youtube_view_count and not keeper.youtube_view_count:
        keeper.youtube_view_count = donor.youtube_view_count
    if donor.wikipedia_title and not keeper.wikipedia_title:
        keeper.wikipedia_title = donor.wikipedia_title
    for field in ("singers", "lyricists", "directors", "actors", "actresses", "moods"):
        existing = list(getattr(keeper, field) or [])
        for item in getattr(donor, field) or []:
            if item not in existing:
                existing.append(item)
        setattr(keeper, field, existing)
    if (donor.popularity or 0) > (keeper.popularity or 0):
        keeper.popularity = donor.popularity


def rehash_all_songs(db: Session) -> dict[str, int]:
    """Recompute content_hash (song|movie); merge collisions with few flushes."""
    songs = db.query(Song).all()
    loaded = len(songs)

    by_hash: dict[str, list[Song]] = defaultdict(list)
    changed = 0
    for song in songs:
        new_h = content_hash(song.song_name, song.movie_name)
        if song.content_hash != new_h:
            changed += 1
        by_hash[new_h].append(song)

    for song in songs:
        song.content_hash = f"tmp-{song.id}"
    db.flush()

    survivors: dict[str, Song] = {}
    pairs: list[tuple[Song, Song, str | None, str | None]] = []
    collision_groups = 0
    for new_h, rows in by_hash.items():
        if len(rows) == 1:
            survivors[new_h] = rows[0]
            continue
        collision_groups += 1
        keeper = _pick_keeper(rows)
        survivors[new_h] = keeper
        for donor in rows:
            if donor.id == keeper.id:
                continue
            pairs.append((keeper, donor, donor.musicbrainz_id, donor.wikidata_id))
            donor.musicbrainz_id = None
            donor.wikidata_id = None
    db.flush()

    deleted = 0
    for keeper, donor, donor_mb, donor_wd in pairs:
        _merge_fields(keeper, donor)
        if donor_wd and not keeper.wikidata_id:
            keeper.wikidata_id = donor_wd
        if donor_mb and not keeper.musicbrainz_id:
            keeper.musicbrainz_id = donor_mb
        db.delete(donor)
        deleted += 1
    db.flush()

    for new_h, song in survivors.items():
        song.content_hash = new_h
    db.commit()

    remaining = db.query(Song).count()
    return {
        "loaded": loaded,
        "hash_values_changed": changed,
        "collision_groups": collision_groups,
        "merged_deleted": deleted,
        "remaining": remaining,
    }
