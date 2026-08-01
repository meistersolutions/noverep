import { registerPlugin } from '@capacitor/core';
import { isAndroidNative } from '@/lib/nativePlatform';
import { api } from '@/lib/api';

interface ResolvedAudioStream {
  url: string;
  title?: string;
  artist?: string;
  duration_seconds?: number;
  mime_type?: string;
  headersJson?: string;
}

interface BackgroundAudioPlugin {
  syncQueue(options: {
    items: Array<{ videoId: string; title?: string; artist?: string; queueItemId?: string }>;
    currentVideoId?: string;
  }): Promise<void>;
  resolveAudioStream(options: { videoId: string }): Promise<ResolvedAudioStream>;
  playStream(options: {
    url: string;
    title?: string;
    artist?: string;
    videoId?: string;
    headers?: Record<string, string>;
    headersJson?: string;
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

async function resolveStreamOnDevice(videoId: string): Promise<ResolvedAudioStream> {
  return BackgroundAudio.resolveAudioStream({ videoId });
}

async function resolveStreamOnServer(videoId: string): Promise<ResolvedAudioStream> {
  const stream = await api.getAudioStream('youtube', videoId);
  return {
    url: stream.url,
    title: stream.title,
    artist: stream.artist,
    duration_seconds: stream.duration_seconds ?? undefined,
    mime_type: stream.mime_type ?? undefined,
    headersJson: stream.http_headers ? JSON.stringify(stream.http_headers) : undefined,
  };
}

function assertPlayableUrl(url: string): void {
  if (!url) throw new Error('No audio stream URL');
  const lower = url.toLowerCase();
  if (lower.includes('storyboard') || lower.includes('ytimg.com/sb/') || lower.includes('i.ytimg.com')) {
    throw new Error('Resolved a non-audio URL');
  }
  if (!/^https?:\/\//i.test(url)) {
    throw new Error('Invalid stream URL scheme');
  }
}

/** NewPipe-style: extract on-device, then play with ExoPlayer (server API is fallback only). */
export async function playNativeAudio(options: {
  videoId: string;
  title?: string;
  artist?: string;
  startAtSec?: number;
}): Promise<void> {
  if (!isAndroidNative()) return;

  let stream: ResolvedAudioStream | null = null;
  let lastError: unknown = null;

  try {
    stream = await resolveStreamOnDevice(options.videoId);
  } catch (err) {
    lastError = err;
    console.warn('[noverep] on-device extract failed, trying server API', err);
    try {
      stream = await resolveStreamOnServer(options.videoId);
    } catch (serverErr) {
      const deviceMsg = err instanceof Error ? err.message : String(err);
      const serverMsg = serverErr instanceof Error ? serverErr.message : String(serverErr);
      throw new Error(`Extract failed (device: ${deviceMsg}; server: ${serverMsg})`);
    }
  }

  if (!stream) {
    throw new Error(lastError instanceof Error ? lastError.message : 'No audio stream');
  }
  assertPlayableUrl(stream.url);

  activeVideoId = options.videoId;
  wantPlaying = true;
  try {
    await BackgroundAudio.playStream({
      url: stream.url,
      title: options.title || stream.title || 'NoRepeat',
      artist: options.artist || stream.artist || 'Playing',
      videoId: options.videoId,
      headersJson: stream.headersJson,
    });
    if (options.startAtSec && options.startAtSec >= 5) {
      // Seek after ExoPlayer has begun buffering the new source.
      setTimeout(() => {
        void seekNativeAudio(options.startAtSec!);
      }, 400);
    }
    void syncNativePlaybackQueue();
  } catch (err) {
    activeVideoId = null;
    wantPlaying = false;
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`ExoPlayer start failed: ${msg}`);
  }
}

/** Push current + upcoming queue to native so skip/auto-next work with WebView suspended. */
export async function syncNativePlaybackQueue(): Promise<void> {
  if (!isAndroidNative()) return;
  try {
    const { usePlayerStore } = await import('@/stores/playerStore');
    const { filterQueueAgainstHeard } = await import('@/lib/heardTracksCache');
    const { queue, currentTrack } = usePlayerStore.getState();
    // Prefer the ExoPlayer video id — store currentTrack can lag during native skips.
    const currentId = activeVideoId || currentTrack?.provider_track_id;
    const items = filterQueueAgainstHeard(queue, currentId)
      .filter((q) => q.provider_track_id)
      .map((q) => ({
        videoId: q.provider_track_id,
        title: q.title,
        artist: q.artist,
        queueItemId: q.id,
      }));

    // Ensure current track is in the list even if queue is briefly empty/out of sync.
    if (currentId && !items.some((i) => i.videoId === currentId)) {
      const meta =
        currentTrack?.provider_track_id === currentId
          ? currentTrack
          : queue.find((q) => q.provider_track_id === currentId);
      items.unshift({
        videoId: currentId,
        title: meta?.title || 'NoRepeat',
        artist: meta?.artist || 'Playing',
        queueItemId: meta && 'id' in meta ? String(meta.id) : '',
      });
    }

    await BackgroundAudio.syncQueue({
      items,
      currentVideoId: currentId || undefined,
    });
  } catch (err) {
    console.warn('[noverep] syncNativePlaybackQueue failed', err);
  }
}

export function noteNativeTrackPlaying(videoId: string): void {
  if (!videoId) return;
  activeVideoId = videoId;
  wantPlaying = true;
  void import('@/lib/youtubePlayerController').then(({ setActiveVideoIdFromNative }) => {
    setActiveVideoIdFromNative(videoId);
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
