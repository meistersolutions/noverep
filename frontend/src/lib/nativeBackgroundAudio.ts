import { registerPlugin } from '@capacitor/core';
import { isAndroidNative } from '@/lib/nativePlatform';
import { api } from '@/lib/api';

interface BackgroundAudioPlugin {
  playStream(options: {
    url: string;
    title?: string;
    artist?: string;
    headers?: Record<string, string>;
  }): Promise<void>;
  pause(): Promise<void>;
  resume(): Promise<void>;
  stop(): Promise<void>;
  seek(options: { seconds: number }): Promise<void>;
  getStatus(): Promise<{ playing: boolean; position: number; duration: number }>;
  start(options: { title?: string; artist?: string; playing?: boolean }): Promise<void>;
  update(options: { title?: string; artist?: string; playing?: boolean }): Promise<void>;
}

const BackgroundAudio = registerPlugin<BackgroundAudioPlugin>('BackgroundAudio');

let activeVideoId: string | null = null;
let wantPlaying = false;

export function isNativeAudioActive(): boolean {
  return isAndroidNative() && !!activeVideoId;
}

export function getNativeAudioVideoId(): string | null {
  return activeVideoId;
}

/** NewPipe-style: resolve stream URL then play with ExoPlayer foreground service. */
export async function playNativeAudio(options: {
  videoId: string;
  title?: string;
  artist?: string;
}): Promise<void> {
  if (!isAndroidNative()) return;
  const stream = await api.getAudioStream('youtube', options.videoId);
  if (!stream?.url) {
    throw new Error('No audio stream URL');
  }
  const lower = stream.url.toLowerCase();
  if (
    lower.includes('storyboard') ||
    lower.includes('ytimg.com') ||
    /\.(jpg|jpeg|png|webp|gif)(\?|$)/.test(lower)
  ) {
    throw new Error('Server returned a non-audio URL — redeploy API stream fix');
  }
  activeVideoId = options.videoId;
  wantPlaying = true;
  await BackgroundAudio.playStream({
    url: stream.url,
    title: options.title || stream.title || 'NoRepeat',
    artist: options.artist || stream.artist || 'Playing',
    headers: stream.http_headers || undefined,
  });
}

export async function pauseNativeAudio(): Promise<void> {
  if (!isAndroidNative()) return;
  wantPlaying = false;
  try {
    await BackgroundAudio.pause();
  } catch {
    /* ignore */
  }
}

export async function resumeNativeAudio(): Promise<void> {
  if (!isAndroidNative() || !activeVideoId) return;
  wantPlaying = true;
  try {
    await BackgroundAudio.resume();
  } catch {
    /* ignore */
  }
}

export async function stopNativeAudio(): Promise<void> {
  if (!isAndroidNative()) return;
  wantPlaying = false;
  activeVideoId = null;
  try {
    await BackgroundAudio.stop();
  } catch {
    /* ignore */
  }
}

export async function seekNativeAudio(seconds: number): Promise<void> {
  if (!isAndroidNative()) return;
  try {
    await BackgroundAudio.seek({ seconds });
  } catch {
    /* ignore */
  }
}

export async function getNativeAudioStatus(): Promise<{
  playing: boolean;
  position: number;
  duration: number;
} | null> {
  if (!isAndroidNative()) return null;
  try {
    return await BackgroundAudio.getStatus();
  } catch {
    return null;
  }
}

export function wantsNativePlaying(): boolean {
  return wantPlaying;
}

/** @deprecated keep for older keep-alive paths */
export async function syncNativeBackgroundAudio(options: {
  playing: boolean;
  title?: string;
  artist?: string;
}): Promise<void> {
  if (!isAndroidNative()) return;
  if (options.playing) await resumeNativeAudio();
  else await pauseNativeAudio();
}

export async function stopNativeBackgroundAudio(): Promise<void> {
  await stopNativeAudio();
}
