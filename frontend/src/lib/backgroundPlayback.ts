import { isAutoResumeAllowed, isUsingNativePlayer, resumePlayback } from '@/lib/youtubePlayerController';
import { isAndroidNative, isNativeApp } from '@/lib/nativePlatform';
import {
  pauseNativeAudio,
  stopNativeBackgroundAudio,
  syncNativeBackgroundAudio,
  noteNativeTrackPlaying,
  syncNativePlaybackQueue,
} from '@/lib/nativeBackgroundAudio';
import { markUsingNativePlayer, setActiveVideoIdFromNative } from '@/lib/youtubePlayerController';
import { usePlayerStore } from '@/stores/playerStore';
import toast from 'react-hot-toast';

let keepAliveTimer: ReturnType<typeof setInterval> | null = null;
let wakeLock: WakeLockSentinel | null = null;
let appStateListener: { remove: () => void } | null = null;
let mediaEventBound = false;

/** Native shells suspend WebViews aggressively — retry often while playing. */
const KEEP_ALIVE_MS = isAndroidNative() ? 800 : isNativeApp ? 2000 : 3000;

async function requestWakeLock() {
  if (!('wakeLock' in navigator)) return;
  try {
    wakeLock = await navigator.wakeLock.request('screen');
    wakeLock.addEventListener('release', () => {
      wakeLock = null;
    });
  } catch {
    /* denied or unsupported */
  }
}

async function releaseWakeLock() {
  if (wakeLock) {
    await wakeLock.release().catch(() => {});
    wakeLock = null;
  }
}

function resumeIfPlaying(getIsPlaying: () => boolean) {
  if (!getIsPlaying() || !isAutoResumeAllowed()) return;
  resumePlayback();
}

function startKeepAlive(getIsPlaying: () => boolean) {
  if (keepAliveTimer) return;
  keepAliveTimer = setInterval(() => {
    const store = usePlayerStore.getState();
    const shouldPlay = getIsPlaying() || store.isPlaying;
    if (!shouldPlay || !isAutoResumeAllowed()) return;

    // ExoPlayer runs in a foreground service — don't spam resume in foreground.
    if (isUsingNativePlayer()) {
      if (document.hidden) resumePlayback();
      return;
    }

    if (document.hidden || isAndroidNative()) {
      resumePlayback();
    }
  }, KEEP_ALIVE_MS);
}

function stopKeepAlive() {
  if (keepAliveTimer) {
    clearInterval(keepAliveTimer);
    keepAliveTimer = null;
  }
}

function ensureNativeServicePlaying() {
  if (!isUsingNativePlayer()) return;
  const track = usePlayerStore.getState().currentTrack;
  void syncNativeBackgroundAudio({
    playing: true,
    title: track?.title,
    artist: track?.artist,
  });
}

async function bindCapacitorAppState(getIsPlaying: () => boolean) {
  if (!isNativeApp || appStateListener) return;

  try {
    const { App } = await import('@capacitor/app');
    appStateListener = await App.addListener('appStateChange', ({ isActive }) => {
      if (isActive) {
        resumeIfPlaying(getIsPlaying);
        if (!getIsPlaying()) stopKeepAlive();
      } else if (getIsPlaying() || usePlayerStore.getState().isPlaying) {
        // ExoPlayer should keep going; only nudge resume + keep-alive for iframe fallback.
        if (isUsingNativePlayer()) {
          ensureNativeServicePlaying();
        } else {
          resumePlayback();
          startKeepAlive(getIsPlaying);
        }
      }
    });
  } catch {
    /* plugin unavailable */
  }
}

function bindNativeMediaControls() {
  if (!isAndroidNative() || mediaEventBound) return;
  mediaEventBound = true;

  window.addEventListener('noverep-media', ((event: CustomEvent<{
    action: string;
    videoId?: string;
    title?: string;
    artist?: string;
    queueItemId?: string;
    reason?: string;
  }>) => {
    const action = event.detail?.action;
    const store = usePlayerStore.getState();
    if (action === 'play') store.setPlaying(true);
    if (action === 'pause') store.setPlaying(false);
    if (action === 'next') void store.next(true);
    if (action === 'previous') void store.previous();
    if (action === 'resume-background') {
      if (store.isPlaying || isAutoResumeAllowed()) {
        if (isUsingNativePlayer()) {
          ensureNativeServicePlaying();
        } else {
          resumePlayback();
          startKeepAlive(() => usePlayerStore.getState().isPlaying);
        }
      }
    }
    if (action === 'ended') {
      void store.next(false);
    }
    if (action === 'track-changed' && event.detail?.videoId) {
      // Native already started the next/prev stream — only sync JS state + API.
      // Await adopt first so syncNativePlaybackQueue pins the new videoId (not the old one).
      noteNativeTrackPlaying(event.detail.videoId);
      setActiveVideoIdFromNative(event.detail.videoId);
      markUsingNativePlayer(true);
      void store
        .adoptNativeTrackChange({
          videoId: event.detail.videoId,
          title: event.detail.title,
          artist: event.detail.artist,
          queueItemId: event.detail.queueItemId,
          reason: event.detail.reason || 'next',
          prevVideoId: event.detail.prevVideoId,
          prevPositionSec: event.detail.prevPositionSec,
          prevDurationSec: event.detail.prevDurationSec,
        })
        .then(() => syncNativePlaybackQueue());
    }
    if (action === 'error') {
      toast.error('Playback failed — try another song');
      store.setPlaying(false);
    }
  }) as EventListener);
}

export function initBackgroundPlayback(getIsPlaying: () => boolean) {
  void bindCapacitorAppState(getIsPlaying);
  bindNativeMediaControls();

  const onVisibility = () => {
    if (document.hidden) {
      if (getIsPlaying() || usePlayerStore.getState().isPlaying) {
        if (isUsingNativePlayer()) {
          ensureNativeServicePlaying();
        } else {
          resumePlayback();
          startKeepAlive(getIsPlaying);
          requestWakeLock();
        }
      }
    } else {
      if (!getIsPlaying()) stopKeepAlive();
      resumeIfPlaying(getIsPlaying);
    }
  };

  const onPageShow = () => resumeIfPlaying(getIsPlaying);

  document.addEventListener('visibilitychange', onVisibility);
  window.addEventListener('pageshow', onPageShow);
  window.addEventListener('focus', onPageShow);

  return () => {
    document.removeEventListener('visibilitychange', onVisibility);
    window.removeEventListener('pageshow', onPageShow);
    window.removeEventListener('focus', onPageShow);
    stopKeepAlive();
    releaseWakeLock();
    appStateListener?.remove();
    appStateListener = null;
    void stopNativeBackgroundAudio();
  };
}

export function onPlaybackStateChange(isPlaying: boolean, getIsPlaying: () => boolean) {
  if (isPlaying) {
    if (isUsingNativePlayer()) {
      // Foreground service owns playback; keep-alive only needed if we leave the app.
      return;
    }
    requestWakeLock();
    startKeepAlive(getIsPlaying);
    void syncNativeBackgroundAudio({
      playing: true,
      title: usePlayerStore.getState().currentTrack?.title,
      artist: usePlayerStore.getState().currentTrack?.artist,
    });
    return;
  }

  // If the page is hidden, a "paused" signal is often from Android/YouTube —
  // keep the service + keep-alive and force resume instead of tearing down.
  if (document.hidden && isAutoResumeAllowed()) {
    if (isUsingNativePlayer()) {
      ensureNativeServicePlaying();
    } else {
      resumePlayback();
      startKeepAlive(getIsPlaying);
      ensureNativeServicePlaying();
    }
    return;
  }

  stopKeepAlive();
  releaseWakeLock();
  if (isAndroidNative() && isUsingNativePlayer()) {
    void pauseNativeAudio();
  } else if (!isAndroidNative()) {
    void stopNativeBackgroundAudio();
  }
}
