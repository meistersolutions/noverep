import { isAutoResumeAllowed, resumePlayback } from '@/lib/youtubePlayerController';
import { isNativeApp } from '@/lib/nativePlatform';

let keepAliveTimer: ReturnType<typeof setInterval> | null = null;
let wakeLock: WakeLockSentinel | null = null;
let appStateListener: { remove: () => void } | null = null;

/** Native shells suspend WebViews aggressively — retry occasionally while playing. */
const KEEP_ALIVE_MS = isNativeApp ? 2000 : 3000;

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
    if (document.hidden && getIsPlaying() && isAutoResumeAllowed()) {
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

async function bindCapacitorAppState(getIsPlaying: () => boolean) {
  if (!isNativeApp || appStateListener) return;

  try {
    const { App } = await import('@capacitor/app');
    appStateListener = await App.addListener('appStateChange', ({ isActive }) => {
      if (isActive) {
        resumeIfPlaying(getIsPlaying);
        stopKeepAlive();
      } else if (getIsPlaying() && isAutoResumeAllowed()) {
        resumePlayback();
        startKeepAlive(getIsPlaying);
      }
    });
  } catch {
    /* plugin unavailable */
  }
}

export function initBackgroundPlayback(getIsPlaying: () => boolean) {
  void bindCapacitorAppState(getIsPlaying);

  const onVisibility = () => {
    if (document.hidden) {
      if (getIsPlaying() && isAutoResumeAllowed()) {
        resumePlayback();
        startKeepAlive(getIsPlaying);
        requestWakeLock();
      }
    } else {
      stopKeepAlive();
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
  };
}

export function onPlaybackStateChange(isPlaying: boolean, getIsPlaying: () => boolean) {
  if (isPlaying) {
    requestWakeLock();
    if (document.hidden && isAutoResumeAllowed()) startKeepAlive(getIsPlaying);
  } else {
    stopKeepAlive();
    releaseWakeLock();
  }
}
