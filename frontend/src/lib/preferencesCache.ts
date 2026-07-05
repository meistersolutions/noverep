import type { UserPreferences } from '@/lib/api';

const PREFS_CACHE_KEY = 'noverep_preferences_cache';

export function readCachedPreferences(): UserPreferences | null {
  try {
    const raw = localStorage.getItem(PREFS_CACHE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as UserPreferences;
  } catch {
    return null;
  }
}

export function writeCachedPreferences(preferences: UserPreferences): void {
  try {
    localStorage.setItem(PREFS_CACHE_KEY, JSON.stringify(preferences));
  } catch {
    /* storage full or private mode */
  }
}

export function clearCachedPreferences(): void {
  localStorage.removeItem(PREFS_CACHE_KEY);
}
