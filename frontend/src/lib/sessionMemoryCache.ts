import type { QueueItem, Track } from '@/lib/api';

const QUEUE_CACHE_KEY = 'noverep_queue_cache';
const HOME_CACHE_KEY = 'noverep_home_cache';
const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

export interface CachedQueueSnapshot {
  queue: QueueItem[];
  currentTrack: QueueItem | Track | null;
  playbackMode?: 'discovery' | 'playlist';
  activePlaylistId?: string | null;
  savedAt: number;
}

export interface HomeSection {
  title: string;
  tracks: Track[];
}

export interface CachedHomeSnapshot {
  sections: HomeSection[];
  savedAt: number;
}

function isFresh(savedAt: number): boolean {
  return Number.isFinite(savedAt) && Date.now() - savedAt < MAX_AGE_MS;
}

export function readCachedQueue(): CachedQueueSnapshot | null {
  try {
    const raw = localStorage.getItem(QUEUE_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedQueueSnapshot;
    if (!parsed?.queue || !Array.isArray(parsed.queue) || !isFresh(parsed.savedAt)) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeCachedQueue(snapshot: Omit<CachedQueueSnapshot, 'savedAt'>): void {
  try {
    const payload: CachedQueueSnapshot = { ...snapshot, savedAt: Date.now() };
    localStorage.setItem(QUEUE_CACHE_KEY, JSON.stringify(payload));
  } catch {
    /* storage full or private mode */
  }
}

export function clearCachedQueue(): void {
  try {
    localStorage.removeItem(QUEUE_CACHE_KEY);
  } catch {
    /* ignore */
  }
}

export function readCachedHome(): CachedHomeSnapshot | null {
  try {
    const raw = localStorage.getItem(HOME_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedHomeSnapshot;
    if (!parsed?.sections || !Array.isArray(parsed.sections) || !isFresh(parsed.savedAt)) return null;
    if (!parsed.sections.length) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeCachedHome(sections: HomeSection[]): void {
  try {
    const payload: CachedHomeSnapshot = { sections, savedAt: Date.now() };
    localStorage.setItem(HOME_CACHE_KEY, JSON.stringify(payload));
  } catch {
    /* storage full or private mode */
  }
}

export function clearCachedHome(): void {
  try {
    localStorage.removeItem(HOME_CACHE_KEY);
  } catch {
    /* ignore */
  }
}

export function clearSessionContentCaches(): void {
  clearCachedQueue();
  clearCachedHome();
}
