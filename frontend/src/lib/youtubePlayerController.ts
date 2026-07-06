/** Singleton YouTube IFrame player – survives React re-renders. */

import { isMobileBrowser } from '@/lib/nativePlatform';

export interface YTPlayerInstance {
  loadVideoById: (videoId: string) => void;
  cueVideoById: (videoId: string) => void;
  playVideo: () => void;
  pauseVideo: () => void;
  seekTo: (seconds: number, allowSeekAhead: boolean) => void;
  setVolume: (volume: number) => void;
  getCurrentTime: () => number;
  getDuration: () => number;
  getPlayerState: () => number;
  getVideoData: () => { video_id: string };
  destroy: () => void;
}

const YT_PLAYING = 1;
const YT_PAUSED = 2;
const YT_BUFFERING = 3;
const YT_ENDED = 0;
const YT_CUED = 5;

let player: YTPlayerInstance | null = null;
let apiReady = false;
let playerReady = false;
let activeVideoId: string | null = null;
let prefetchedVideoId: string | null = null;
let ignoreEndedUntil = 0;
let wantPlaying = false;
/** When false, ignore PAUSED events that would auto-resume (user pressed pause). */
let allowAutoResume = true;
let playbackGeneration = 0;
let onNaturalEnd: (() => void) | null = null;
let onPlayingChange: ((playing: boolean) => void) | null = null;
let onActiveVideoId: ((videoId: string) => void) | null = null;

const apiWaiters: Array<() => void> = [];
const playerWaiters: Array<() => void> = [];
const backgroundRetryMs = [400, 800, 1500, 2500];

function notify(waiters: Array<() => void>) {
  waiters.splice(0).forEach((cb) => cb());
}

function isActivelyPlaying(): boolean {
  if (!player || !activeVideoId) return false;
  const state = player.getPlayerState?.();
  return state === YT_PLAYING || state === YT_BUFFERING;
}

function notifyActiveVideo(videoId: string) {
  if (!videoId) return;
  activeVideoId = videoId;
  onActiveVideoId?.(videoId);
}

let apiScriptRequested = false;

export function ensureYouTubeApiScript(): void {
  if (window.YT?.Player) {
    apiReady = true;
    return;
  }
  if (document.getElementById('youtube-iframe-api')) return;

  apiScriptRequested = true;
  const tag = document.createElement('script');
  tag.id = 'youtube-iframe-api';
  tag.src = 'https://www.youtube.com/iframe_api';
  tag.async = true;
  document.head.appendChild(tag);
}

export function warmUpPlayback(): void {
  ensureYouTubeApiScript();
}

export async function ensurePlaybackReady(timeoutMs = 20000): Promise<boolean> {
  try {
    ensureYouTubeApiScript();
    await waitForYouTubeApi();
    await waitForPlayer(timeoutMs);
    return Boolean(player);
  } catch {
    return false;
  }
}

export function waitForYouTubeApi(): Promise<void> {
  if (apiReady && window.YT?.Player) return Promise.resolve();
  ensureYouTubeApiScript();
  return new Promise((resolve) => {
    const settle = () => {
      if (!window.YT?.Player) return false;
      apiReady = true;
      resolve();
      return true;
    };
    if (settle()) return;

    const prev = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      apiReady = true;
      prev?.();
      notify(apiWaiters);
    };
    apiWaiters.push(resolve);

    // API may load before our callback is assigned (common on fast desktop networks).
    if (settle()) {
      notify(apiWaiters);
      return;
    }

    const started = Date.now();
    const poll = window.setInterval(() => {
      if (settle()) {
        clearInterval(poll);
        notify(apiWaiters);
      } else if (Date.now() - started > 30000) {
        clearInterval(poll);
      }
    }, 100);
  });
}

export function waitForPlayer(timeoutMs = 30000): Promise<void> {
  if (playerReady && player) return Promise.resolve();
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (fn: () => void) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      fn();
    };
    const timer =
      timeoutMs > 0
        ? setTimeout(
            () => finish(() => reject(new Error('YouTube player not ready'))),
            timeoutMs,
          )
        : null;
    playerWaiters.push(() => finish(resolve));
  });
}

export function setPlayerInstance(instance: YTPlayerInstance | null) {
  player = instance;
  playerReady = instance !== null;
  if (playerReady) notify(playerWaiters);
}

export function getPlayer(): YTPlayerInstance | null {
  return player;
}

export function getActiveVideoId(): string | null {
  if (!player?.getVideoData) return activeVideoId;
  try {
    const id = player.getVideoData()?.video_id;
    return id || activeVideoId;
  } catch {
    return activeVideoId;
  }
}

export function isAutoResumeAllowed(): boolean {
  return allowAutoResume && wantPlaying;
}

export function prepareTrackTransition() {
  wantPlaying = true;
  allowAutoResume = true;
  playbackGeneration += 1;
  ignoreEndedUntil = Date.now() + 5000;
  prefetchedVideoId = null;
}

export function setWantPlaying(playing: boolean) {
  wantPlaying = playing;
  if (!playing) allowAutoResume = false;
}

export function setOnNaturalEnd(cb: (() => void) | null) {
  onNaturalEnd = cb;
}

export function setOnPlayingChange(cb: ((playing: boolean) => void) | null) {
  onPlayingChange = cb;
}

export function setOnActiveVideoId(cb: ((videoId: string) => void) | null) {
  onActiveVideoId = cb;
}

function schedulePlayRetries(videoId: string, generation: number) {
  if (!allowAutoResume) return;
  const mobile = isMobileBrowser();
  const delays = document.hidden
    ? backgroundRetryMs
    : mobile
      ? [0, 80, 200, 500, 1000, 2000, 3500]
      : [0, 400, 1200];
  delays.forEach((ms) => {
    setTimeout(() => {
      if (generation !== playbackGeneration) return;
      attemptPlay(videoId, generation);
    }, ms);
  });
}

function attemptPlay(videoId: string, generation = playbackGeneration) {
  if (!player || generation !== playbackGeneration) return;
  if (!allowAutoResume || !wantPlaying) return;
  if (activeVideoId !== videoId) return;
  const state = player.getPlayerState?.();
  if (state !== YT_PLAYING) {
    player.playVideo();
  }
}

/** Buffer the upcoming track — never interrupt a song that is already playing. */
export function prefetchVideo(videoId: string) {
  if (!player || !playerReady || !videoId) return;
  if (videoId === activeVideoId || videoId === prefetchedVideoId) return;
  if (isActivelyPlaying()) return;

  try {
    player.cueVideoById(videoId);
    prefetchedVideoId = videoId;
  } catch {
    prefetchedVideoId = null;
  }
}

/** After reload: load video into player paused so play button works. */
export async function cueVideoForResume(videoId: string, volume = 80): Promise<void> {
  await waitForYouTubeApi();
  await waitForPlayer();
  if (!player || !videoId) return;

  playbackGeneration += 1;
  wantPlaying = false;
  allowAutoResume = false;
  activeVideoId = videoId;
  prefetchedVideoId = null;
  player.setVolume(volume);

  try {
    const state = player.getPlayerState?.();
    const loadedId = player.getVideoData?.()?.video_id;
    if (loadedId === videoId && (state === YT_PAUSED || state === YT_CUED || state === YT_PLAYING)) {
      if (state === YT_PLAYING) player.pauseVideo();
      return;
    }
    player.cueVideoById(videoId);
  } catch {
    player.cueVideoById(videoId);
  }
}

/** YouTube fires ENDED when switching videos – ignore those spurious events. */
export function handlePlayerStateChange(state: number, target: YTPlayerInstance) {
  if (state === YT_PLAYING) {
    const videoId = target.getVideoData?.()?.video_id;
    if (videoId) notifyActiveVideo(videoId);
    onPlayingChange?.(true);
    ignoreEndedUntil = Date.now() + 3000;
    return;
  }

  if (state === YT_PAUSED) {
    if (allowAutoResume && wantPlaying) {
      attemptPlay(activeVideoId ?? '');
      return;
    }
    onPlayingChange?.(false);
    return;
  }

  if (state === YT_CUED) {
    const videoId = target.getVideoData?.()?.video_id;
    if (videoId && videoId === prefetchedVideoId && isActivelyPlaying()) {
      return;
    }
    if (allowAutoResume && wantPlaying && videoId === activeVideoId) {
      attemptPlay(videoId);
    }
    return;
  }

  if (state === YT_ENDED) {
    if (Date.now() < ignoreEndedUntil) return;

    const duration = target.getDuration?.() ?? 0;
    const current = target.getCurrentTime?.() ?? 0;

    if (duration > 0 && current < Math.min(duration * 0.9, duration - 5)) return;

    wantPlaying = false;
    allowAutoResume = false;
    onPlayingChange?.(false);
    onNaturalEnd?.();
  }
}

export async function loadAndPlay(videoId: string, volume = 80): Promise<void> {
  ensureYouTubeApiScript();
  await waitForYouTubeApi();
  await waitForPlayer(isMobileBrowser() ? 25000 : 30000);
  if (!player) throw new Error('YouTube player unavailable');

  const generation = ++playbackGeneration;
  wantPlaying = true;
  allowAutoResume = true;
  ignoreEndedUntil = Date.now() + 5000;
  player.setVolume(volume);

  const usePrefetched = prefetchedVideoId === videoId;
  activeVideoId = videoId;
  prefetchedVideoId = null;
  notifyActiveVideo(videoId);

  if (usePrefetched) {
    attemptPlay(videoId, generation);
    schedulePlayRetries(videoId, generation);
    return;
  }

  player.loadVideoById(videoId);
  attemptPlay(videoId, generation);
  schedulePlayRetries(videoId, generation);
}

export function pausePlayback() {
  wantPlaying = false;
  allowAutoResume = false;
  playbackGeneration += 1;
  player?.pauseVideo();
}

export function resumePlayback() {
  if (!player || !activeVideoId) return;
  wantPlaying = true;
  allowAutoResume = true;
  const state = player.getPlayerState?.();
  if (state === YT_PLAYING) return;
  player.playVideo();
}

export function seekPlayback(seconds: number) {
  player?.seekTo(seconds, true);
}

export function setVolumeLevel(volume: number) {
  player?.setVolume(volume);
}
