import { isAutoResumeAllowed, resumePlayback } from '@/lib/youtubePlayerController';
import { isAndroidNative, isNativeApp } from '@/lib/nativePlatform';
import {
  stopNativeBackgroundAudio,
  syncNativeBackgroundAudio,
} from '@/lib/nativeBackgroundAudio';
import { usePlayerStore } from '@/stores/playerStore';

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
    if ((document.hidden || isAndroidNative()) && shouldPlay && isAutoResumeAllowed()) {
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
        // Keep service if still playing; don't stop keep-alive until foreground settles
        if (!getIsPlaying()) stopKeepAlive();
      } else if (getIsPlaying() || usePlayerStore.getState().isPlaying) {
        resumePlayback();
        startKeepAlive(getIsPlaying);
        ensureNativeServicePlaying();
      }
    });
  } catch {
    /* plugin unavailable */
  }
}

function bindNativeMediaControls() {
  if (!isAndroidNative() || mediaEventBound) return;
  mediaEventBound = true;

  window.addEventListener('noverep-media', ((event: CustomEvent<{ action: string }>) => {
    const action = event.detail?.action;
    const store = usePlayerStore.getState();
    if (action === 'play') store.setPlaying(true);
    if (action === 'pause') store.setPlaying(false);
    if (action === 'next') void store.next(true);
    if (action === 'previous') void store.previous();
    if (action === 'resume-background') {
      if (store.isPlaying || isAutoResumeAllowed()) {
        resumePlayback();
        startKeepAlive(() => usePlayerStore.getState().isPlaying);
        ensureNativeServicePlaying();
      }
    }
    if (action === 'ended') {
      void store.next(false);
    }
  }) as EventListener);
}

export function initBackgroundPlayback(getIsPlaying: () => boolean) {
  void bindCapacitorAppState(getIsPlaying);
  bindNativeMediaControls();

  const onVisibility = () => {
    if (document.hidden) {
      if (getIsPlaying() || usePlayerStore.getState().isPlaying) {
        resumePlayback();
        startKeepAlive(getIsPlaying);
        requestWakeLock();
        ensureNativeServicePlaying();
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
  const track = usePlayerStore.getState().currentTrack;
  if (isPlaying) {
    requestWakeLock();
    startKeepAlive(getIsPlaying);
    void syncNativeBackgroundAudio({
      playing: true,
      title: track?.title,
      artist: track?.artist,
    });
    return;
  }

  // If the page is hidden, a "paused" signal is often from Android/YouTube —
  // keep the service + keep-alive and force resume instead of tearing down.
  if (document.hidden && isAutoResumeAllowed()) {
    resumePlayback();
    startKeepAlive(getIsPlaying);
    ensureNativeServicePlaying();
    return;
  }

  stopKeepAlive();
  releaseWakeLock();
  void stopNativeBackgroundAudio();
}
