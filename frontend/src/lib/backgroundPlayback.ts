import { resumePlayback } from '@/lib/youtubePlayerController';

let keepAliveTimer: ReturnType<typeof setInterval> | null = null;
let wakeLock: WakeLockSentinel | null = null;

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

function startKeepAlive(getIsPlaying: () => boolean) {
  if (keepAliveTimer) return;
  keepAliveTimer = setInterval(() => {
    if (getIsPlaying() && document.hidden) {
      resumePlayback();
    }
  }, 1000);
}

function stopKeepAlive() {
  if (keepAliveTimer) {
    clearInterval(keepAliveTimer);
    keepAliveTimer = null;
  }
}

export function initBackgroundPlayback(getIsPlaying: () => boolean) {
  const onVisibility = () => {
    if (document.hidden) {
      if (getIsPlaying()) {
        resumePlayback();
        startKeepAlive(getIsPlaying);
        requestWakeLock();
      }
    } else {
      stopKeepAlive();
      if (getIsPlaying()) {
        resumePlayback();
      }
    }
  };

  const onPageShow = () => {
    if (getIsPlaying()) resumePlayback();
  };

  document.addEventListener('visibilitychange', onVisibility);
  window.addEventListener('pageshow', onPageShow);
  window.addEventListener('focus', onPageShow);

  return () => {
    document.removeEventListener('visibilitychange', onVisibility);
    window.removeEventListener('pageshow', onPageShow);
    window.removeEventListener('focus', onPageShow);
    stopKeepAlive();
    releaseWakeLock();
  };
}

export function onPlaybackStateChange(isPlaying: boolean, getIsPlaying: () => boolean) {
  if (isPlaying) {
    requestWakeLock();
    if (document.hidden) startKeepAlive(getIsPlaying);
  } else {
    stopKeepAlive();
    releaseWakeLock();
  }
}
