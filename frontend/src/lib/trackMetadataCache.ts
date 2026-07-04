import type { SongDetails, TrackLyrics } from '@/lib/api';

const detailsCache = new Map<string, SongDetails>();
const lyricsCache = new Map<string, TrackLyrics | 'missing'>();

export function trackCacheKey(provider: string, providerTrackId: string): string {
  return `${provider}:${providerTrackId}`;
}

export function getCachedTrackDetails(key: string): SongDetails | undefined {
  return detailsCache.get(key);
}

export function setCachedTrackDetails(key: string, details: SongDetails): void {
  detailsCache.set(key, details);
}

export function getCachedTrackLyrics(key: string): TrackLyrics | 'missing' | undefined {
  return lyricsCache.get(key);
}

export function setCachedTrackLyrics(key: string, lyrics: TrackLyrics | 'missing'): void {
  lyricsCache.set(key, lyrics);
}
