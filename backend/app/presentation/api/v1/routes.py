import csv
from datetime import UTC
from io import StringIO
from uuid import UUID

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dto.schemas import (
    AddPlaylistTrackRequest,
    AddToQueueRequest,
    AudioStreamResponse,
    CreatePlaylistRequest,
    FeedbackRequest,
    FeedbackResponse,
    GoogleAuthRequest,
    HistoryEntryResponse,
    HomeRecommendationsResponse,
    HomeSectionResponse,
    LoginRequest,
    OnboardingRequest,
    PlayEventRequest,
    LikedStatusResponse,
    LyricsLineResponse,
    LyricsResponse,
    PlaylistDetailResponse,
    PlaylistResponse,
    PlaylistTrackResponse,
    QueueItemResponse,
    RegisterRequest,
    RemoveQueueItemRequest,
    RemoveQueueItemResponse,
    SearchResponse,
    SongDetailsResponse,
    StatisticsResponse,
    TokenResponse,
    TrackResponse,
    UpdatePreferencesRequest,
    UserPreferencesResponse,
)
from app.application.services.home_recommendations import HomeRecommendationService
from app.application.services.memory_service import MemoryService
from app.application.tasks.queue_tasks import run_queue_sync_background
from app.application.services.playlist_service import PlaylistService
from app.application.services.queue_service import QueueRefreshFilters, QueueService
from app.application.services.recommendation_engine import RecommendationEngine
from app.application.services.song_enrichment_service import (
    SongEnrichment,
    SongEnrichmentService,
    enrichment_matches_track,
)
from app.application.services.song_normalizer import SongNormalizer
from app.application.services.statistics_service import StatisticsService
from app.application.tasks.enrichment_tasks import run_song_enrichment_background
from app.config import settings
from app.dependencies import (
    get_auth_service,
    get_current_user,
    get_enrichment_service,
    get_home_recommendations_service,
    get_lyrics_service,
    get_memory_service,
    get_normalizer,
    get_playlist_service,
    get_providers,
    get_queue_service,
    get_recommendation_engine,
    get_statistics_service,
)
from app.infrastructure.auth.auth_service import AuthService, create_access_token
from app.infrastructure.database.models import (
    ArtistModel,
    FeedbackModel,
    ListeningHistoryModel,
    PlaylistModel,
    ProviderMappingModel,
    ProviderModel,
    SessionModel,
    SongModel,
    UserModel,
    UserPreferencesModel,
)
from app.infrastructure.database.session import get_db_session
from app.infrastructure.providers.youtube.metadata_utils import (
    fetch_oembed_metadata,
    is_placeholder_youtube_title,
    pick_display_artist,
    pick_display_title,
)

router = APIRouter()
logger = structlog.get_logger()


def _queue_item_response(item) -> QueueItemResponse:
    return QueueItemResponse(
        id=item.id,
        provider=item.provider,
        provider_track_id=item.provider_track_id,
        title=item.title,
        artist=item.artist,
        album=item.album,
        thumbnail_url=item.thumbnail_url,
        duration_seconds=item.duration_seconds,
        position=item.position,
        is_current=item.is_current,
        canonical_song_id=getattr(item, "song_id", None),
    )

def _track_response(track, score: float | None = None) -> TrackResponse:
    title = (track.title or "Unknown").strip() or "Unknown"
    artist = (track.artist or "Unknown Artist").strip() or "Unknown Artist"
    return TrackResponse(
        provider=track.provider,
        provider_track_id=track.provider_track_id,
        title=title,
        artist=artist,
        album=track.album,
        duration_seconds=track.duration_seconds,
        thumbnail_url=track.thumbnail_url,
        canonical_song_id=track.canonical_song_id,
        score=score,
        content_kind=getattr(track, "content_kind", "song") or "song",
    )


@router.post("/auth/register", response_model=TokenResponse)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthService = Depends(get_auth_service),
):
    try:
        user = await auth.register(session, body.username, body.email, body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = create_access_token(user.id, user.username)
    return TokenResponse(
        access_token=token, user_id=user.id, username=user.username, is_guest=user.is_guest
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthService = Depends(get_auth_service),
):
    try:
        user = await auth.login(session, body.username, body.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    token = create_access_token(user.id, user.username)
    return TokenResponse(
        access_token=token, user_id=user.id, username=user.username, is_guest=user.is_guest
    )


@router.post("/auth/guest", response_model=TokenResponse)
async def guest_login(
    session: AsyncSession = Depends(get_db_session),
    auth: AuthService = Depends(get_auth_service),
):
    user = await auth.create_guest(session)
    token = create_access_token(user.id, user.username)
    return TokenResponse(
        access_token=token, user_id=user.id, username=user.username, is_guest=True
    )


@router.post("/auth/google", response_model=TokenResponse)
async def google_auth(
    body: GoogleAuthRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthService = Depends(get_auth_service),
):
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
        from app.config import settings

        if not settings.google_client_id:
            raise HTTPException(status_code=501, detail="Google login not configured")

        idinfo = google_id_token.verify_oauth2_token(
            body.id_token, google_requests.Request(), settings.google_client_id
        )
        user = await auth.google_login(
            session,
            google_id=idinfo["sub"],
            email=idinfo.get("email", ""),
            name=idinfo.get("name", "User"),
            avatar=idinfo.get("picture"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Google auth failed: {e}")

    token = create_access_token(user.id, user.username)
    return TokenResponse(
        access_token=token, user_id=user.id, username=user.username, is_guest=user.is_guest
    )


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=1),
    provider: str = "youtube",
    limit: int = Query(default=20, le=50),
    include_heard: bool = Query(default=False),
    quick: bool = Query(default=True, description="Fast search without full DB pipeline"),
    raw: bool = Query(
        default=True,
        description="Literal search without user preferences (song filter only)",
    ),
    any_video: bool = Query(
        default=False,
        description="Search any YouTube video (not limited to single songs)",
    ),
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    engine: RecommendationEngine = Depends(get_recommendation_engine),
):
    scored = []
    try:
        if raw:
            scored = await engine.raw_search(
                q, provider_name=provider, limit=limit, any_video=any_video
            )
        elif quick:
            scored = await engine.quick_search(
                session,
                user.id,
                q,
                provider_name=provider,
                limit=limit,
                skip_memory_filter=include_heard,
            )
        else:
            scored = await engine.recommend(
                session,
                user.id,
                q,
                provider_name=provider,
                limit=limit,
                skip_memory_filter=include_heard,
            )
    except Exception as e:
        logger.exception("search_failed", query=q, quick=quick, raw=raw, error=str(e))
        if raw:
            try:
                scored = await engine.quick_search(
                    session,
                    user.id,
                    q,
                    provider_name=provider,
                    limit=limit,
                    skip_memory_filter=include_heard,
                )
            except Exception as fallback_err:
                logger.exception(
                    "search_fallback_failed", query=q, error=str(fallback_err)
                )
                raise HTTPException(
                    status_code=503,
                    detail="Search is temporarily unavailable. Please try again.",
                ) from fallback_err
        elif quick:
            try:
                scored = await engine.recommend(
                    session,
                    user.id,
                    q,
                    provider_name=provider,
                    limit=limit,
                    skip_memory_filter=include_heard,
                )
            except Exception as fallback_err:
                logger.exception(
                    "search_fallback_failed", query=q, error=str(fallback_err)
                )
                raise HTTPException(
                    status_code=503,
                    detail="Search is temporarily unavailable. Please try again.",
                ) from fallback_err
        else:
            raise HTTPException(
                status_code=503,
                detail="Search is temporarily unavailable. Please try again.",
            ) from e
    results = [_track_response(c.track, c.score) for c in scored]
    return SearchResponse(query=q, results=results, total=len(results))


@router.get("/tracks/audio-stream", response_model=AudioStreamResponse)
async def track_audio_stream(
    provider: str = Query(default="youtube"),
    provider_track_id: str = Query(..., min_length=1),
    user: UserModel = Depends(get_current_user),
    providers=Depends(get_providers),
):
    """Direct audio URL for native background playback (Android ExoPlayer)."""
    provider_impl = providers.get(provider)
    if not provider_impl:
        raise HTTPException(status_code=400, detail="Unknown provider")
    if not hasattr(provider_impl, "get_audio_stream"):
        raise HTTPException(status_code=400, detail="Provider does not support audio streams")
    try:
        data = await provider_impl.get_audio_stream(provider_track_id)
    except Exception as e:
        logger.exception("audio_stream_failed", provider=provider, track_id=provider_track_id)
        raise HTTPException(
            status_code=503,
            detail=f"Could not resolve audio stream: {e}",
        ) from e
    return AudioStreamResponse(**data)


@router.get("/tracks/details", response_model=SongDetailsResponse)
async def track_details(
    background_tasks: BackgroundTasks,
    provider: str = Query(default="youtube"),
    provider_track_id: str = Query(..., min_length=1),
    title: str | None = None,
    artist: str | None = None,
    refresh: bool = False,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    providers=Depends(get_providers),
    normalizer: SongNormalizer = Depends(get_normalizer),
    enrichment: SongEnrichmentService = Depends(get_enrichment_service),
):
    from app.domain.entities import ProviderTrack

    provider_impl = providers.get(provider)
    if not provider_impl:
        raise HTTPException(status_code=400, detail="Unknown provider")

    track: ProviderTrack | None = None
    song = await normalizer._find_by_provider_track(
        session,
        ProviderTrack(
            provider=provider,
            provider_track_id=provider_track_id,
            title=title or "",
            artist=artist or "",
            album=None,
            duration_seconds=None,
            thumbnail_url=None,
        ),
    )

    if song and song.enrichment_metadata and not refresh:
        metadata = song.enrichment_metadata
        artist_name = artist or ""
        if not artist_name and song.artist_id:
            artist_row = await session.execute(
                select(ArtistModel).where(ArtistModel.id == song.artist_id)
            )
            artist_model = artist_row.scalar_one_or_none()
            artist_name = artist_model.name if artist_model else ""
        cached = SongEnrichment.from_dict(metadata)
        probe_track = ProviderTrack(
            provider=provider,
            provider_track_id=provider_track_id,
            title=title or song.title,
            artist=artist_name,
            album=None,
            duration_seconds=song.duration_seconds,
            thumbnail_url=None,
        )
        if cached and enrichment_matches_track(cached, probe_track):
            return SongDetailsResponse(
                title=title or song.title,
                artist=artist_name,
                album=None,
                song_name=metadata.get("song_name") or song.title,
                composed_by=list(metadata.get("composed_by") or []),
                lyricist_by=list(metadata.get("lyricist_by") or []),
                performed_by=list(metadata.get("performed_by") or []),
                movie_name=metadata.get("movie_name"),
                release_year=metadata.get("release_year") or song.release_year,
                musicbrainz_id=metadata.get("musicbrainz_id") or song.musicbrainz_id,
                canonical_song_id=song.id,
            )

    try:
        track = await provider_impl.get_metadata(provider_track_id)
    except Exception as e:
        if not song:
            raise HTTPException(status_code=404, detail="Track not found") from e
        track = ProviderTrack(
            provider=provider,
            provider_track_id=provider_track_id,
            title=title or song.title,
            artist=artist or "",
            album=None,
            duration_seconds=song.duration_seconds,
            thumbnail_url=None,
        )

    if not song:
        song = await normalizer.resolve_canonical(track, session)

    enriched = None
    if settings.musicbrainz_enabled:
        enriched = await enrichment.get_for_song(
            session,
            song.id,
            track,
            refresh=refresh,
        )

    metadata = enriched.to_dict() if enriched else (song.enrichment_metadata or {})
    return SongDetailsResponse(
        title=track.title,
        artist=track.artist,
        album=track.album,
        song_name=metadata.get("song_name") or song.title,
        composed_by=list(metadata.get("composed_by") or []),
        lyricist_by=list(metadata.get("lyricist_by") or []),
        performed_by=list(metadata.get("performed_by") or []),
        movie_name=metadata.get("movie_name"),
        release_year=metadata.get("release_year") or song.release_year,
        musicbrainz_id=metadata.get("musicbrainz_id") or song.musicbrainz_id,
        canonical_song_id=song.id,
    )


@router.get("/tracks/lyrics", response_model=LyricsResponse | None)
async def track_lyrics(
    provider: str = Query(default="youtube"),
    provider_track_id: str = Query(..., min_length=1),
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    duration_seconds: int | None = None,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    providers=Depends(get_providers),
    normalizer: SongNormalizer = Depends(get_normalizer),
    enrichment: SongEnrichmentService = Depends(get_enrichment_service),
    lyrics_svc=Depends(get_lyrics_service),
):
    if not settings.lrclib_enabled:
        raise HTTPException(status_code=404, detail="Lyrics disabled")

    from app.application.services.song_matcher import extract_movie_hint
    from app.domain.entities import ProviderTrack

    track: ProviderTrack | None = None
    if not title or not artist:
        provider_impl = providers.get(provider)
        if provider_impl:
            try:
                track = await provider_impl.get_metadata(provider_track_id)
                title = title or track.title
                artist = artist or track.artist
                album = album or track.album
                duration_seconds = duration_seconds or track.duration_seconds
            except Exception:
                pass

    if not title or not artist:
        raise HTTPException(status_code=400, detail="title and artist are required")

    if not track:
        track = ProviderTrack(
            provider=provider,
            provider_track_id=provider_track_id,
            title=title,
            artist=artist,
            album=album,
            duration_seconds=duration_seconds,
            thumbnail_url=None,
        )

    song = await normalizer._find_by_provider_track(session, track)
    lyrics_title = title
    lyrics_artist = artist
    lyrics_album = album or extract_movie_hint(title, artist, album)

    if song and settings.musicbrainz_enabled:
        enriched = await enrichment.get_for_song(session, song.id, track)
        if enriched and enrichment_matches_track(enriched, track):
            lyrics_title = enriched.song_name or lyrics_title
            if enriched.performed_by:
                lyrics_artist = enriched.performed_by[0]
            lyrics_album = enriched.movie_name or lyrics_album

    result = await lyrics_svc.fetch_lyrics(
        lyrics_title,
        lyrics_artist,
        lyrics_album,
        duration_seconds,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Lyrics not found")

    return LyricsResponse(
        synced=result.synced,
        plain=result.plain,
        lines=[LyricsLineResponse(time_ms=line.time_ms, text=line.text) for line in result.lines],
        instrumental=result.instrumental,
        source=result.source,
    )


@router.get("/queue", response_model=list[QueueItemResponse])
async def get_queue(
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    queue_svc: QueueService = Depends(get_queue_service),
):
    items = await queue_svc.get_queue(session, user.id)
    return [_queue_item_response(i) for i in items]


@router.post("/queue", response_model=QueueItemResponse)
async def add_to_queue(
    body: AddToQueueRequest,
    background_tasks: BackgroundTasks,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    providers=Depends(get_providers),
    queue_svc: QueueService = Depends(get_queue_service),
):
    provider = providers.get(body.provider)
    if not provider:
        raise HTTPException(status_code=400, detail="Unknown provider")
    track = await provider.get_metadata(
        body.provider_track_id,
        songs_only=not body.audio_only,
    )
    try:
        item = await queue_svc.add_to_queue(
            session, user.id, track,
            explicitly_requested=body.explicitly_requested,
            play_now=body.play_now,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if settings.musicbrainz_enabled and item.song_id and not body.audio_only:
        background_tasks.add_task(
            run_song_enrichment_background,
            item.song_id,
            item.provider,
            item.provider_track_id,
            item.title,
            item.artist,
            item.album,
            item.duration_seconds,
        )
    return _queue_item_response(item)


@router.post("/queue/next", response_model=QueueItemResponse | None)
async def queue_next(
    background_tasks: BackgroundTasks,
    seed: str | None = None,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    queue_svc: QueueService = Depends(get_queue_service),
):
    item = await queue_svc.next_track(session, user.id, seed_query=seed, defer_sync=True)
    if item and not await queue_svc._is_playlist_mode(session, user.id):
        background_tasks.add_task(run_queue_sync_background, user.id)
    if not item:
        return None
    return _queue_item_response(item)


@router.post("/queue/previous", response_model=QueueItemResponse | None)
async def queue_previous(
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    queue_svc: QueueService = Depends(get_queue_service),
):
    item = await queue_svc.previous_track(session, user.id)
    if not item:
        return None
    return _queue_item_response(item)


@router.post("/queue/play/{item_id}", response_model=QueueItemResponse)
async def play_queue_item(
    item_id: UUID,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    queue_svc: QueueService = Depends(get_queue_service),
):
    item = await queue_svc.play_queue_item(session, user.id, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    return _queue_item_response(item)


@router.post("/queue/{item_id}/remove", response_model=RemoveQueueItemResponse)
async def remove_queue_item(
    item_id: UUID,
    body: RemoveQueueItemRequest,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    queue_svc: QueueService = Depends(get_queue_service),
    memory: MemoryService = Depends(get_memory_service),
):
    queue = await queue_svc.get_queue(session, user.id)
    target = next((q for q in queue if q.id == item_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Queue item not found")

    sess_result = await session.execute(
        select(SessionModel).where(SessionModel.id == body.session_id)
    )
    if not sess_result.scalar_one_or_none():
        session.add(
            SessionModel(id=body.session_id, user_id=user.id, device_id=None)
        )
        await session.flush()

    if target.song_id:
        await memory.record_play(
            session,
            user_id=user.id,
            song_id=target.song_id,
            provider=target.provider,
            artist=target.artist,
            album=target.album,
            genre=None,
            session_id=body.session_id,
            duration_listened=body.duration_listened,
            completion_pct=body.completion_pct,
            skipped=True,
            device_id=None,
            explicitly_requested=False,
        )

    result = await queue_svc.remove_queue_item(session, user.id, item_id)
    if not result:
        raise HTTPException(status_code=404, detail="Queue item not found")

    return RemoveQueueItemResponse(
        was_current=result.was_current,
        next_item=_queue_item_response(result.next_item) if result.next_item else None,
        queue=[_queue_item_response(i) for i in result.queue],
    )


@router.post("/queue/play-next", response_model=QueueItemResponse)
async def play_next_in_queue(
    body: AddToQueueRequest,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    providers=Depends(get_providers),
    queue_svc: QueueService = Depends(get_queue_service),
):
    provider = providers.get(body.provider)
    if not provider:
        raise HTTPException(status_code=400, detail="Unknown provider")
    track = await provider.get_metadata(
        body.provider_track_id,
        songs_only=not body.audio_only,
    )
    try:
        item = await queue_svc.insert_play_next(
            session, user.id, track, explicitly_requested=body.explicitly_requested
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _queue_item_response(item)


@router.post("/queue/refresh", response_model=list[QueueItemResponse])
async def refresh_queue(
    seed: str | None = Query(default=None, description="Search query to seed upcoming tracks"),
    from_preferences: bool = Query(default=False, description="Seed from user preferences instead"),
    languages: str | None = Query(
        default=None, description="Comma-separated language codes for this refresh"
    ),
    year_from: int | None = Query(default=None, ge=1900, le=2100),
    year_to: int | None = Query(default=None, ge=1900, le=2100),
    include_heard: bool = Query(
        default=False, description="Include songs heard within memory window"
    ),
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    queue_svc: QueueService = Depends(get_queue_service),
):
    if from_preferences and seed:
        raise HTTPException(status_code=400, detail="Use either seed or from_preferences, not both")

    lang_list = [s.strip() for s in languages.split(",") if s.strip()] if languages else None
    filters = QueueRefreshFilters(
        preferred_languages=lang_list,
        year_from=year_from,
        year_to=year_to,
        skip_memory_filter=include_heard,
    ) if (lang_list or year_from is not None or year_to is not None or include_heard) else None

    items = await queue_svc.refresh_upcoming(
        session,
        user.id,
        seed_query=seed,
        from_preferences=from_preferences,
        filters=filters,
    )
    return [_queue_item_response(i) for i in items]


@router.post("/queue/sync", response_model=list[QueueItemResponse])
async def sync_queue(
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    queue_svc: QueueService = Depends(get_queue_service),
):
    items = await queue_svc.sync_queue(session, user.id)
    return [_queue_item_response(i) for i in items]


@router.post("/queue/fill")
async def fill_queue(
    minimum: int = Query(default=20, le=50),
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    queue_svc: QueueService = Depends(get_queue_service),
):
    await queue_svc.ensure_queue_size(session, user.id, minimum=minimum)
    items = await queue_svc.get_queue(session, user.id)
    return [_queue_item_response(i) for i in items]


@router.delete("/queue")
async def clear_queue(
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    queue_svc: QueueService = Depends(get_queue_service),
):
    await queue_svc.clear_queue(session, user.id)
    return {"ok": True}


@router.post("/playback/event")
async def record_playback(
    body: PlayEventRequest,
    background_tasks: BackgroundTasks,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    memory: MemoryService = Depends(get_memory_service),
    normalizer: SongNormalizer = Depends(get_normalizer),
    providers=Depends(get_providers),
):
    provider = providers.get(body.provider)
    if not provider:
        raise HTTPException(status_code=400, detail="Unknown provider")

    # Ensure listening session exists (FK requirement)
    sess_result = await session.execute(
        select(SessionModel).where(SessionModel.id == body.session_id)
    )
    if not sess_result.scalar_one_or_none():
        session.add(
            SessionModel(id=body.session_id, user_id=user.id, device_id=body.device_id)
        )
        await session.flush()

    # Resolve song – merge provider metadata with client title/artist (yt-dlp on cloud often returns placeholders)
    from app.domain.entities import ProviderTrack

    try:
        fetched = await provider.get_metadata(body.provider_track_id)
    except Exception:
        fetched = None

    if fetched:
        track = ProviderTrack(
            provider=fetched.provider,
            provider_track_id=fetched.provider_track_id,
            title=pick_display_title(fetched.title, body.title),
            artist=pick_display_artist(fetched.artist, body.artist),
            album=fetched.album or body.album,
            duration_seconds=fetched.duration_seconds,
            thumbnail_url=fetched.thumbnail_url,
            stream_url=fetched.stream_url,
            genre=body.genre or fetched.genre,
            language=fetched.language,
            release_year=fetched.release_year,
            isrc=fetched.isrc,
            popularity=fetched.popularity,
        )
    else:
        track = ProviderTrack(
            provider=body.provider,
            provider_track_id=body.provider_track_id,
            title=body.title,
            artist=body.artist,
            album=body.album,
            duration_seconds=None,
            thumbnail_url=None,
            genre=body.genre,
        )

    song = await normalizer.resolve_canonical(track, session)
    if settings.musicbrainz_enabled and body.duration_listened == 0:
        background_tasks.add_task(
            run_song_enrichment_background,
            song.id,
            track.provider,
            track.provider_track_id,
            track.title,
            track.artist,
            track.album,
            track.duration_seconds,
        )
    entry = await memory.record_play(
        session,
        user_id=user.id,
        song_id=song.id,
        provider=body.provider,
        artist=body.artist,
        album=body.album,
        genre=body.genre,
        session_id=body.session_id,
        duration_listened=body.duration_listened,
        completion_pct=body.completion_pct,
        skipped=body.skipped,
        device_id=body.device_id,
        explicitly_requested=body.explicitly_requested,
    )
    return {"id": entry.id, "song_id": song.id}


@router.get("/history", response_model=list[HistoryEntryResponse])
async def get_history(
    limit: int = Query(default=50, le=200),
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    from sqlalchemy.orm import aliased

    youtube_mapping = aliased(ProviderMappingModel)
    youtube_provider_ids = select(ProviderModel.id).where(ProviderModel.name == "youtube")

    result = await session.execute(
        select(
            ListeningHistoryModel,
            SongModel.title,
            youtube_mapping.provider_track_id,
        )
        .join(SongModel, ListeningHistoryModel.song_id == SongModel.id)
        .outerjoin(
            youtube_mapping,
            (youtube_mapping.song_id == SongModel.id)
            & youtube_mapping.provider_id.in_(youtube_provider_ids),
        )
        .where(ListeningHistoryModel.user_id == user.id)
        .order_by(ListeningHistoryModel.played_at.desc())
        .limit(limit)
    )
    rows = result.all()
    seen_songs: set[UUID] = set()
    entries: list[HistoryEntryResponse] = []
    oembed_cache: dict[str, tuple[str, str]] = {}
    for h, title, video_id in rows:
        if h.song_id in seen_songs:
            continue
        seen_songs.add(h.song_id)
        display_title = title
        if is_placeholder_youtube_title(display_title) and video_id:
            if video_id not in oembed_cache:
                meta = fetch_oembed_metadata(video_id)
                oembed_cache[video_id] = meta if meta else ("", "")
            oembed_title, _ = oembed_cache[video_id]
            if oembed_title:
                display_title = oembed_title
        entries.append(
            HistoryEntryResponse(
                id=h.id,
                title=display_title,
                artist=h.artist_name,
                album=h.album_name,
                genre=h.genre_name,
                provider=h.provider,
                played_at=h.played_at,
                duration_listened=h.duration_listened,
                completion_pct=h.completion_pct,
                skipped=h.skipped,
            )
        )
    return entries


@router.get("/history/export.csv")
async def export_history_csv(
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(
        select(
            ListeningHistoryModel.played_at,
            SongModel.title,
            SongModel.enrichment_metadata,
        )
        .join(SongModel, ListeningHistoryModel.song_id == SongModel.id)
        .where(ListeningHistoryModel.user_id == user.id)
        .order_by(ListeningHistoryModel.played_at.desc())
    )
    rows = result.all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Time", "Song Name", "Movie Name", "Composer", "Singers"])

    for played_at, song_title, enrichment_metadata in rows:
        metadata = enrichment_metadata or {}
        song_name = (metadata.get("song_name") or song_title or "").strip()
        movie_name = (metadata.get("movie_name") or "").strip()
        composed_by = ", ".join(metadata.get("composed_by") or [])
        singers = ", ".join(metadata.get("performed_by") or [])
        if played_at:
            dt = played_at.astimezone(UTC) if played_at.tzinfo else played_at.replace(tzinfo=UTC)
            date_str = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%H:%M:%S")
        else:
            date_str = ""
            time_str = ""
        writer.writerow([date_str, time_str, song_name, movie_name, composed_by, singers])

    filename = f"history-{user.username}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/preferences", response_model=UserPreferencesResponse)
async def get_preferences(
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(
        select(UserPreferencesModel).where(UserPreferencesModel.user_id == user.id)
    )
    prefs = result.scalar_one_or_none()
    if not prefs:
        raise HTTPException(status_code=404, detail="Preferences not found")
    return UserPreferencesResponse(
        memory_window=prefs.memory_window,
        repeat_disabled=prefs.repeat_disabled,
        autoplay=prefs.autoplay,
        shuffle=prefs.shuffle,
        theme=prefs.theme,
        language_preference=prefs.language_preference,
        preferred_languages=prefs.preferred_languages or [],
        active_search_query=getattr(prefs, "active_search_query", None),
        favorite_artists=prefs.favorite_artists or [],
        onboarding_completed=getattr(prefs, "onboarding_completed", False) or False,
        preferred_genres=prefs.preferred_genres or [],
        blocked_artists=prefs.blocked_artists or [],
        blocked_songs=prefs.blocked_songs or [],
        blocked_albums=prefs.blocked_albums or [],
        recommendation_weights=prefs.recommendation_weights or {},
        crossfade_enabled=prefs.crossfade_enabled,
        gapless_enabled=prefs.gapless_enabled,
        discovery_year_from=getattr(prefs, "discovery_year_from", None),
        discovery_year_to=getattr(prefs, "discovery_year_to", None),
        playback_mode=getattr(prefs, "playback_mode", None) or "discovery",
        active_playlist_id=getattr(prefs, "active_playlist_id", None),
    )


@router.patch("/preferences", response_model=UserPreferencesResponse)
async def update_preferences(
    body: UpdatePreferencesRequest,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(
        select(UserPreferencesModel).where(UserPreferencesModel.user_id == user.id)
    )
    prefs = result.scalar_one_or_none()
    if not prefs:
        raise HTTPException(status_code=404, detail="Preferences not found")
    updates = body.model_dump(exclude_unset=True)
    from app.application.services.language_utils import (
        normalize_language_code,
        normalize_language_list,
    )

    if "language_preference" in updates and updates["language_preference"] is not None:
        updates["language_preference"] = normalize_language_code(updates["language_preference"])
    if "preferred_languages" in updates and updates["preferred_languages"] is not None:
        updates["preferred_languages"] = normalize_language_list(updates["preferred_languages"])
    if updates.get("active_search_query") == "":
        updates["active_search_query"] = None
    for field, value in updates.items():
        setattr(prefs, field, value)
    await session.flush()
    return await get_preferences(user, session)


@router.get("/statistics", response_model=StatisticsResponse)
async def statistics(
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    stats: StatisticsService = Depends(get_statistics_service),
):
    data = await stats.get_dashboard(session, user.id)
    return StatisticsResponse(**data)


@router.get("/playlists", response_model=list[PlaylistResponse])
async def list_playlists(
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    playlist_svc: PlaylistService = Depends(get_playlist_service),
):
    await playlist_svc.ensure_liked_playlist(session, user.id)
    result = await session.execute(
        select(PlaylistModel).where(PlaylistModel.user_id == user.id)
    )
    playlists = list(result.scalars().all())
    playlists.sort(key=lambda p: (0 if p.system_key == "liked" else 1, p.created_at))
    return [
        PlaylistResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            is_public=p.is_public,
            is_system=getattr(p, "is_system", False) or False,
            system_key=getattr(p, "system_key", None),
            created_at=p.created_at,
        )
        for p in playlists
    ]


@router.get("/playlists/liked/status", response_model=LikedStatusResponse)
async def liked_status(
    provider: str = "youtube",
    provider_track_id: str = Query(min_length=1),
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    playlist_svc: PlaylistService = Depends(get_playlist_service),
):
    playlist = await playlist_svc.ensure_liked_playlist(session, user.id)
    liked = await playlist_svc.is_track_liked(
        session, user.id, provider, provider_track_id
    )
    return LikedStatusResponse(liked=liked, playlist_id=playlist.id)


@router.post("/playlists/liked/tracks")
async def add_liked_track(
    body: AddPlaylistTrackRequest,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    providers=Depends(get_providers),
    playlist_svc: PlaylistService = Depends(get_playlist_service),
):
    provider = providers.get(body.provider)
    if not provider:
        raise HTTPException(status_code=400, detail="Unknown provider")

    from app.domain.entities import ProviderTrack

    if body.title and body.artist:
        track = ProviderTrack(
            provider=body.provider,
            provider_track_id=body.provider_track_id,
            title=body.title,
            artist=body.artist,
            album=body.album,
            duration_seconds=body.duration_seconds,
            thumbnail_url=body.thumbnail_url,
        )
    else:
        try:
            track = await provider.get_metadata(body.provider_track_id)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not load track: {e}")

    item, already_liked = await playlist_svc.add_to_liked(session, user.id, track)
    return {"ok": True, "already_liked": already_liked, "item_id": str(item.id)}


@router.post("/playlists", response_model=PlaylistResponse)
async def create_playlist(
    body: CreatePlaylistRequest,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    playlist = PlaylistModel(
        user_id=user.id, name=body.name, description=body.description, is_public=body.is_public
    )
    session.add(playlist)
    await session.flush()
    return PlaylistResponse(
        id=playlist.id,
        name=playlist.name,
        description=playlist.description,
        is_public=playlist.is_public,
        is_system=False,
        system_key=None,
        created_at=playlist.created_at,
    )


@router.get("/playlists/{playlist_id}", response_model=PlaylistDetailResponse)
async def get_playlist(
    playlist_id: UUID,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    playlist_svc: PlaylistService = Depends(get_playlist_service),
):
    playlist = await playlist_svc.get_user_playlist(session, user.id, playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")

    from app.infrastructure.database.models import PlaylistItemModel

    items_result = await session.execute(
        select(PlaylistItemModel)
        .where(PlaylistItemModel.playlist_id == playlist_id)
        .order_by(PlaylistItemModel.position)
    )
    items = items_result.scalars().all()
    tracks: list[PlaylistTrackResponse] = []
    for item in items:
        track = await playlist_svc._song_to_track(session, item.song_id)
        if track:
            tracks.append(
                PlaylistTrackResponse(
                    id=item.id,
                    provider=track.provider,
                    provider_track_id=track.provider_track_id,
                    title=track.title,
                    artist=track.artist,
                    album=track.album,
                    thumbnail_url=track.thumbnail_url,
                    duration_seconds=track.duration_seconds,
                    position=item.position,
                )
            )

    return PlaylistDetailResponse(
        id=playlist.id,
        name=playlist.name,
        description=playlist.description,
        is_public=playlist.is_public,
        is_system=getattr(playlist, "is_system", False) or False,
        system_key=getattr(playlist, "system_key", None),
        created_at=playlist.created_at,
        track_count=len(tracks),
        tracks=tracks,
    )


@router.post("/playlists/{playlist_id}/tracks")
async def add_playlist_track(
    playlist_id: UUID,
    body: AddPlaylistTrackRequest,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    providers=Depends(get_providers),
    playlist_svc: PlaylistService = Depends(get_playlist_service),
):
    provider = providers.get(body.provider)
    if not provider:
        raise HTTPException(status_code=400, detail="Unknown provider")

    from app.domain.entities import ProviderTrack

    if body.title and body.artist:
        track = ProviderTrack(
            provider=body.provider,
            provider_track_id=body.provider_track_id,
            title=body.title,
            artist=body.artist,
            album=body.album,
            duration_seconds=body.duration_seconds,
            thumbnail_url=body.thumbnail_url,
        )
    else:
        try:
            track = await provider.get_metadata(body.provider_track_id)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not load track: {e}")
    try:
        item = await playlist_svc.add_track(session, user.id, playlist_id, track)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True, "item_id": str(item.id)}


@router.post("/playlists/{playlist_id}/play", response_model=list[QueueItemResponse])
async def play_playlist(
    playlist_id: UUID,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    playlist_svc: PlaylistService = Depends(get_playlist_service),
    queue_svc: QueueService = Depends(get_queue_service),
):
    tracks = await playlist_svc.get_playlist_tracks(session, user.id, playlist_id)
    if not tracks:
        raise HTTPException(status_code=400, detail="Playlist is empty")
    items = await queue_svc.load_playlist_queue(session, user.id, playlist_id, tracks)
    return [_queue_item_response(i) for i in items]


@router.get("/me")
async def get_me(user: UserModel = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name or user.username,
        "email": user.email,
        "is_guest": user.is_guest,
        "is_admin": user.is_admin,
        "avatar_url": user.avatar_url,
    }


@router.post("/onboarding")
async def complete_onboarding(
    body: OnboardingRequest,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    user.display_name = body.display_name
    result = await session.execute(
        select(UserPreferencesModel).where(UserPreferencesModel.user_id == user.id)
    )
    prefs = result.scalar_one_or_none()
    if not prefs:
        raise HTTPException(status_code=404, detail="Preferences not found")

    from app.application.services.language_utils import (
        normalize_language_code,
        normalize_language_list,
        resolve_languages,
    )

    if body.preferred_languages:
        langs = normalize_language_list(body.preferred_languages)
    elif body.language_preference:
        code = normalize_language_code(body.language_preference)
        langs = resolve_languages(code)
    else:
        langs = resolve_languages("all")

    prefs.favorite_artists = body.favorite_artists
    prefs.preferred_languages = langs
    prefs.language_preference = (
        "all" if len(langs) >= 7 else langs[0] if len(langs) == 1 else "multi"
    )
    prefs.onboarding_completed = True
    await session.flush()

    return {
        "ok": True,
        "display_name": user.display_name,
        "favorite_artists": prefs.favorite_artists,
        "preferred_languages": prefs.preferred_languages,
        "language_preference": prefs.language_preference,
    }


@router.get("/recommendations/home", response_model=HomeRecommendationsResponse)
async def home_recommendations(
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    home_svc: HomeRecommendationService = Depends(get_home_recommendations_service),
):
    import asyncio

    try:
        sections = await asyncio.wait_for(
            home_svc.get_home_sections(session, user.id),
            timeout=70.0,
        )
    except asyncio.TimeoutError:
        logger.warning("home_recommendations_timeout", user_id=str(user.id))
        sections = []
    return HomeRecommendationsResponse(
        sections=[HomeSectionResponse(title=s["title"], tracks=s["tracks"]) for s in sections]
    )


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    entry = FeedbackModel(
        user_id=user.id,
        feedback_type=body.feedback_type,
        title=body.title,
        description=body.description,
        contact_email=body.contact_email,
    )
    session.add(entry)
    await session.flush()
    return FeedbackResponse(
        id=entry.id,
        feedback_type=entry.feedback_type,
        title=entry.title,
        status=entry.status,
        created_at=entry.created_at,
    )


@router.get("/feedback/mine", response_model=list[FeedbackResponse])
async def my_feedback(
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(
        select(FeedbackModel)
        .where(FeedbackModel.user_id == user.id)
        .order_by(FeedbackModel.created_at.desc())
        .limit(20)
    )
    return [
        FeedbackResponse(
            id=f.id,
            feedback_type=f.feedback_type,
            title=f.title,
            status=f.status,
            created_at=f.created_at,
            admin_response=f.admin_response,
            responded_at=f.responded_at,
        )
        for f in result.scalars()
    ]
