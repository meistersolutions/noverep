/** Persist last playback position so a track can resume after app restart. */

const KEY = 'noverep_playback_position';
const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

interface SavedPosition {
  videoId: string;
  positionSec: number;
  durationSec: number;
  savedAt: number;
}

export function savePlaybackPosition(
  videoId: string,
  positionSec: number,
  durationSec: number,
): void {
  if (!videoId || !Number.isFinite(positionSec) || positionSec < 5) return;
  if (durationSec > 0 && positionSec / durationSec >= 0.92) {
    clearPlaybackPosition(videoId);
    return;
  }
  try {
    const payload: SavedPosition = {
      videoId,
      positionSec: Math.floor(positionSec),
      durationSec: Math.floor(durationSec || 0),
      savedAt: Date.now(),
    };
    localStorage.setItem(KEY, JSON.stringify(payload));
  } catch {
    /* ignore */
  }
}

/** Return resume offset (seconds) for this video, or null. Consumes the save. */
export function takeResumePosition(videoId: string): number | null {
  if (!videoId) return null;
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SavedPosition;
    if (!parsed?.videoId || parsed.videoId !== videoId) return null;
    if (!Number.isFinite(parsed.savedAt) || Date.now() - parsed.savedAt > MAX_AGE_MS) {
      localStorage.removeItem(KEY);
      return null;
    }
    if (!Number.isFinite(parsed.positionSec) || parsed.positionSec < 5) return null;
    localStorage.removeItem(KEY);
    return parsed.positionSec;
  } catch {
    return null;
  }
}

export function clearPlaybackPosition(videoId?: string): void {
  try {
    if (!videoId) {
      localStorage.removeItem(KEY);
      return;
    }
    const raw = localStorage.getItem(KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw) as SavedPosition;
    if (parsed?.videoId === videoId) localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

export function peekPlaybackPosition(videoId: string): number | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SavedPosition;
    if (parsed?.videoId !== videoId) return null;
    if (!Number.isFinite(parsed.savedAt) || Date.now() - parsed.savedAt > MAX_AGE_MS) return null;
    return Number.isFinite(parsed.positionSec) && parsed.positionSec >= 5
      ? parsed.positionSec
      : null;
  } catch {
    return null;
  }
}
