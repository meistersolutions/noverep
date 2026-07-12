import { api, Track } from '@/lib/api';
import { markTrackHeardLocally } from '@/lib/heardTracksCache';

export async function recordPlayStart(
  track: Track,
  sessionId: string,
  explicitlyRequested = false,
): Promise<void> {
  if (!explicitlyRequested) {
    markTrackHeardLocally(track.provider_track_id);
  }
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
    explicitly_requested: explicitlyRequested,
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
  markTrackHeardLocally(track.provider_track_id);
  await api.recordPlayback({
    provider: track.provider,
    provider_track_id: track.provider_track_id,
    title: track.title,
    artist: track.artist,
    album: track.album,
    duration_listened: Math.floor(Math.max(0, currentTime)),
    completion_pct: pct,
    skipped,
    session_id: sessionId,
    explicitly_requested: false,
  });
}
