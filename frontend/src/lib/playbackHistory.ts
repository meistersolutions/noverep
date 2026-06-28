import { api, Track } from '@/lib/api';

export async function recordPlayStart(
  track: Track,
  sessionId: string,
): Promise<void> {
  await api.recordPlayback({
    provider: track.provider,
    provider_track_id: track.provider_track_id,
    title: track.title,
    artist: track.artist,
    album: track.album,
    duration_listened: 0,
    completion_pct: 0,
    skipped: false,
    session_id: sessionId,
    explicitly_requested: true,
  });
}

export async function recordPlayProgress(
  track: Track,
  sessionId: string,
  currentTime: number,
  duration: number,
  skipped = false,
): Promise<void> {
  const pct = duration > 0 ? Math.min(100, (currentTime / duration) * 100) : 0;
  await api.recordPlayback({
    provider: track.provider,
    provider_track_id: track.provider_track_id,
    title: track.title,
    artist: track.artist,
    album: track.album,
    duration_listened: Math.floor(currentTime),
    completion_pct: pct,
    skipped,
    session_id: sessionId,
    explicitly_requested: !skipped,
  });
}
