"""Enrich songs with MusicBrainz metadata for filtering and display."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.song_matcher import extract_core_title, match_score, normalize_text
from app.domain.entities import ProviderTrack
from app.infrastructure.database.models import ArtistModel, SongModel
from app.infrastructure.external.musicbrainz_client import (
    COMPOSER_REL_TYPES,
    MusicBrainzClient,
)

logger = structlog.get_logger()


@dataclass
class SongEnrichment:
    musicbrainz_id: str | None = None
    song_name: str | None = None
    composed_by: list[str] = field(default_factory=list)
    performed_by: list[str] = field(default_factory=list)
    movie_name: str | None = None
    release_year: int | None = None
    source: str = "musicbrainz"

    def to_dict(self) -> dict[str, Any]:
        return {
            "musicbrainz_id": self.musicbrainz_id,
            "song_name": self.song_name,
            "composed_by": self.composed_by,
            "performed_by": self.performed_by,
            "movie_name": self.movie_name,
            "release_year": self.release_year,
            "source": self.source,
            "enriched_at": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SongEnrichment | None:
        if not data:
            return None
        return cls(
            musicbrainz_id=data.get("musicbrainz_id"),
            song_name=data.get("song_name"),
            composed_by=list(data.get("composed_by") or []),
            performed_by=list(data.get("performed_by") or []),
            movie_name=data.get("movie_name"),
            release_year=data.get("release_year"),
            source=data.get("source", "musicbrainz"),
        )


def _parse_year(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(ch for ch in value[:10] if ch.isdigit())
    if len(digits) >= 4:
        year = int(digits[:4])
        if 1900 <= year <= 2100:
            return year
    return None


def _artist_credit_names(recording: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for credit in recording.get("artist-credit") or []:
        artist = credit.get("artist") or {}
        name = (artist.get("name") or credit.get("name") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _release_group_movie_name(recording: dict[str, Any]) -> str | None:
    for release in recording.get("releases") or []:
        group = release.get("release-group")
        groups = [group] if isinstance(group, dict) else (group or [])
        for item in groups:
            if not isinstance(item, dict):
                continue
            primary = (item.get("primary-type") or "").lower()
            secondary = [str(s).lower() for s in (item.get("secondary-types") or [])]
            title = (item.get("title") or "").strip()
            if not title:
                continue
            if primary == "soundtrack" or "soundtrack" in secondary:
                return title
    for release in recording.get("releases") or []:
        title = (release.get("title") or "").strip()
        if title:
            return title
    return None


def _relation_artist_names(relations: list[dict[str, Any]], allowed_types: frozenset[str]) -> list[str]:
    names: list[str] = []
    for rel in relations or []:
        rel_type = (rel.get("type") or "").lower()
        if rel_type not in allowed_types:
            continue
        artist = rel.get("artist") or {}
        name = (artist.get("name") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _pick_best_recording(
    candidates: list[dict[str, Any]],
    title: str,
    artist: str,
    duration_seconds: int | None,
) -> dict[str, Any] | None:
    if not candidates:
        return None

    core_title = extract_core_title(title, artist)
    best: dict[str, Any] | None = None
    best_score = 0.0

    for candidate in candidates:
        cand_title = candidate.get("title") or ""
        cand_artists = _artist_credit_names(candidate)
        cand_artist = ", ".join(cand_artists[:2]) if cand_artists else ""
        cand_duration = None
        if candidate.get("length"):
            cand_duration = int(candidate["length"]) // 1000

        score = match_score(
            core_title,
            artist,
            duration_seconds,
            cand_title,
            cand_artist,
            cand_duration,
        )
        if score > best_score:
            best_score = score
            best = candidate

    return best if best_score >= 0.72 else None


class SongEnrichmentService:
    def __init__(self, client: MusicBrainzClient):
        self.client = client

    async def enrich_track(self, track: ProviderTrack) -> SongEnrichment | None:
        core_title = extract_core_title(track.title, track.artist)
        candidates = await self.client.search_recording(
            core_title,
            track.artist,
            track.duration_seconds,
        )
        if not candidates:
            candidates = await self.client.search_recording(core_title, None, track.duration_seconds)
        if not candidates:
            return None

        picked = _pick_best_recording(candidates, core_title, track.artist, track.duration_seconds)
        if not picked or not picked.get("id"):
            return None

        recording = await self.client.lookup_recording(picked["id"])
        if not recording:
            return None

        return await self._parse_recording(recording)

    async def _parse_recording(self, recording: dict[str, Any]) -> SongEnrichment:
        mbid = recording.get("id")
        performed_by = _artist_credit_names(recording)
        composed_by: list[str] = []

        for rel in recording.get("relations") or []:
            if rel.get("type") != "performance":
                continue
            work = rel.get("work")
            if not work or not work.get("id"):
                continue
            work_data = await self.client.lookup_work(work["id"])
            if not work_data:
                continue
            composed_by.extend(
                _relation_artist_names(work_data.get("relations") or [], COMPOSER_REL_TYPES)
            )

        composed_by = list(dict.fromkeys(composed_by))
        release_year = _parse_year(recording.get("first-release-date"))
        if not release_year:
            for release in recording.get("releases") or []:
                release_year = _parse_year(release.get("date"))
                if release_year:
                    break

        return SongEnrichment(
            musicbrainz_id=mbid,
            song_name=(recording.get("title") or "").strip() or None,
            composed_by=composed_by,
            performed_by=performed_by,
            movie_name=_release_group_movie_name(recording),
            release_year=release_year,
        )

    async def enrich_and_persist(
        self,
        session: AsyncSession,
        song: SongModel,
        track: ProviderTrack,
    ) -> SongEnrichment | None:
        if song.enrichment_metadata and song.musicbrainz_id:
            cached = SongEnrichment.from_dict(song.enrichment_metadata)
            if cached:
                return cached

        enrichment = await self.enrich_track(track)
        if not enrichment or not enrichment.musicbrainz_id:
            return None

        existing = await session.execute(
            select(SongModel).where(SongModel.musicbrainz_id == enrichment.musicbrainz_id)
        )
        duplicate = existing.scalar_one_or_none()
        if duplicate and duplicate.id != song.id:
            return SongEnrichment.from_dict(duplicate.enrichment_metadata) or enrichment

        song.musicbrainz_id = enrichment.musicbrainz_id
        song.enrichment_metadata = enrichment.to_dict()
        if enrichment.song_name and enrichment.song_name.strip():
            song.title = enrichment.song_name.strip()
            song.normalized_title = normalize_text(enrichment.song_name)
        if enrichment.release_year and not song.release_year:
            song.release_year = enrichment.release_year
        await session.flush()
        logger.info(
            "song_enriched",
            song_id=str(song.id),
            musicbrainz_id=enrichment.musicbrainz_id,
            movie=enrichment.movie_name,
        )
        return enrichment

    async def get_for_song(
        self,
        session: AsyncSession,
        song_id: UUID,
        track: ProviderTrack | None = None,
        *,
        refresh: bool = False,
    ) -> SongEnrichment | None:
        result = await session.execute(select(SongModel).where(SongModel.id == song_id))
        song = result.scalar_one_or_none()
        if not song:
            return None

        if not refresh and song.enrichment_metadata:
            cached = SongEnrichment.from_dict(song.enrichment_metadata)
            if cached:
                return cached

        if not track:
            artist_name = ""
            if song.artist_id:
                artist_row = await session.execute(
                    select(ArtistModel).where(ArtistModel.id == song.artist_id)
                )
                artist = artist_row.scalar_one_or_none()
                artist_name = artist.name if artist else ""
            track = ProviderTrack(
                provider="youtube",
                provider_track_id="",
                title=song.title,
                artist=artist_name,
                album=None,
                duration_seconds=song.duration_seconds,
                thumbnail_url=None,
            )

        return await self.enrich_and_persist(session, song, track)
