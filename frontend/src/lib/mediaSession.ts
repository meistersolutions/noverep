import type { Track } from '@/lib/api';

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

  try {
    navigator.mediaSession.setActionHandler('play', () => handlers.play());
    navigator.mediaSession.setActionHandler('pause', () => handlers.pause());
    navigator.mediaSession.setActionHandler('nexttrack', () => handlers.next());
    navigator.mediaSession.setActionHandler('previoustrack', () => handlers.previous());
  } catch {
    /* some browsers reject certain handlers */
  }
}
