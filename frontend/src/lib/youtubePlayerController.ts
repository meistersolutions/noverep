/** Singleton YouTube IFrame player – survives React re-renders. */

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
const YT_ENDED = 0;
const YT_CUED = 5;

let player: YTPlayerInstance | null = null;
let apiReady = false;
let playerReady = false;
let activeVideoId: string | null = null;
let prefetchedVideoId: string | null = null;
let ignoreEndedUntil = 0;
let wantPlaying = false;
let onNaturalEnd: (() => void) | null = null;
let onPlayingChange: ((playing: boolean) => void) | null = null;

const apiWaiters: Array<() => void> = [];
const playerWaiters: Array<() => void> = [];
const backgroundRetryMs = [200, 400, 800, 1500, 2500, 4000, 6000, 9000, 12000];

function notify(waiters: Array<() => void>) {
  waiters.splice(0).forEach((cb) => cb());
}

export function waitForYouTubeApi(): Promise<void> {
  if (apiReady && window.YT?.Player) return Promise.resolve();
  return new Promise((resolve) => {
    if (window.YT?.Player) {
      apiReady = true;
      resolve();
      return;
    }
    const prev = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      apiReady = true;
      prev?.();
      notify(apiWaiters);
    };
    apiWaiters.push(resolve);
  });
}

export function waitForPlayer(): Promise<void> {
  if (playerReady && player) return Promise.resolve();
  return new Promise((resolve) => playerWaiters.push(resolve));
}

export function setPlayerInstance(instance: YTPlayerInstance | null) {
  player = instance;
  playerReady = instance !== null;
  if (playerReady) notify(playerWaiters);
}

export function getPlayer(): YTPlayerInstance | null {
  return player;
}

export function setWantPlaying(playing: boolean) {
  wantPlaying = playing;
}

export function setOnNaturalEnd(cb: (() => void) | null) {
  onNaturalEnd = cb;
}

export function setOnPlayingChange(cb: ((playing: boolean) => void) | null) {
  onPlayingChange = cb;
}

function schedulePlayRetries(videoId: string) {
  const delays = document.hidden ? backgroundRetryMs : [200, 600, 1200, 2000, 3500];
  delays.forEach((ms) => {
    setTimeout(() => attemptPlay(videoId), ms);
  });
}

function attemptPlay(videoId: string) {
  if (!player || activeVideoId !== videoId || !wantPlaying) return;
  const state = player.getPlayerState?.();
  if (state !== YT_PLAYING) {
    player.playVideo();
  }
}

/** Buffer the upcoming track so skip/autoplay can start faster. */
export function prefetchVideo(videoId: string) {
  if (!player || !playerReady || !videoId) return;
  if (videoId === activeVideoId || videoId === prefetchedVideoId) return;
  try {
    player.cueVideoById(videoId);
    prefetchedVideoId = videoId;
  } catch {
    prefetchedVideoId = null;
  }
}

/** YouTube fires ENDED when switching videos – ignore those spurious events. */
export function handlePlayerStateChange(state: number, target: YTPlayerInstance) {
  if (state === YT_PLAYING) {
    onPlayingChange?.(true);
    ignoreEndedUntil = Date.now() + 1500;
    return;
  }

  if (state === YT_PAUSED) {
    if (wantPlaying) {
      attemptPlay(activeVideoId ?? '');
      if (document.hidden) {
        schedulePlayRetries(activeVideoId ?? '');
      }
      return;
    }
    onPlayingChange?.(false);
    return;
  }

  if (state === YT_CUED) {
    if (wantPlaying) attemptPlay(activeVideoId ?? '');
    return;
  }

  if (state === YT_ENDED) {
    if (Date.now() < ignoreEndedUntil) return;

    const duration = target.getDuration?.() ?? 0;
    const current = target.getCurrentTime?.() ?? 0;

    if (duration > 0 && current < Math.min(duration * 0.9, duration - 5)) return;

    wantPlaying = false;
    onPlayingChange?.(false);
    onNaturalEnd?.();
  }
}

export async function loadAndPlay(videoId: string, volume = 80): Promise<void> {
  await waitForYouTubeApi();
  await waitForPlayer();
  if (!player) return;

  wantPlaying = true;
  ignoreEndedUntil = Date.now() + 4000;
  player.setVolume(volume);

  const usePrefetched = prefetchedVideoId === videoId;
  activeVideoId = videoId;
  prefetchedVideoId = null;

  if (usePrefetched) {
    attemptPlay(videoId);
    schedulePlayRetries(videoId);
    return;
  }

  player.loadVideoById(videoId);
  attemptPlay(videoId);
  schedulePlayRetries(videoId);
}

export function pausePlayback() {
  wantPlaying = false;
  player?.pauseVideo();
}

export function resumePlayback() {
  wantPlaying = true;
  player?.playVideo();
  if (activeVideoId) schedulePlayRetries(activeVideoId);
}

export function seekPlayback(seconds: number) {
  player?.seekTo(seconds, true);
}

export function setVolumeLevel(volume: number) {
  player?.setVolume(volume);
}
