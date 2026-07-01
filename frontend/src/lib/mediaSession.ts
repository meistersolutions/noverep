import type { Track } from '@/lib/api';
import { seekPlayback } from '@/lib/youtubePlayerController';
import { usePlayerStore } from '@/stores/playerStore';

export function updateMediaSession(track: Track | null, isPlaying: boolean) {
  if (!('mediaSession' in navigator)) return;

  if (!track) {
    navigator.mediaSession.metadata = null;
    navigator.mediaSession.playbackState = 'none';
    return;
  }

  const artwork = track.thumbnail_url
    ? [{ src: track.thumbnail_url, sizes: '512x512', type: 'image/jpeg' as const }]
    : [];

  navigator.mediaSession.metadata = new MediaMetadata({
    title: track.title,
    artist: track.artist,
    album: track.album || 'NoRepeat',
    artwork,
  });
  navigator.mediaSession.playbackState = isPlaying ? 'playing' : 'paused';
}

export function setupMediaSessionHandlers(handlers: {
  play: () => void;
  pause: () => void;
  next: () => void;
  previous: () => void;
}) {
  if (!('mediaSession' in navigator)) return;

  const seekBy = (delta: number) => {
    const { currentTime, duration } = usePlayerStore.getState();
    const next = Math.max(0, Math.min(duration || 0, currentTime + delta));
    seekPlayback(next);
    usePlayerStore.getState().setCurrentTime(next);
  };

  const setHandler = (action: MediaSessionAction, fn: (() => void) | null) => {
    try {
      navigator.mediaSession.setActionHandler(action, fn);
    } catch {
      /* unsupported on this browser */
    }
  };

  setHandler('play', () => handlers.play());
  setHandler('pause', () => handlers.pause());
  setHandler('nexttrack', () => handlers.next());
  setHandler('previoustrack', () => handlers.previous());
  setHandler('seekbackward', () => seekBy(-10));
  setHandler('seekforward', () => seekBy(10));
}
