/** Persist queue page filter controls for the browser session. */

const KEY = 'noverep_queue_filters_v1';

export type QueueFilterSession = {
  languages?: string[];
  yearFrom?: number | null;
  yearTo?: number | null;
  popularityMin?: number;
  popularityMax?: number;
};

export function loadQueueFilterSession(): QueueFilterSession | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    return parsed as QueueFilterSession;
  } catch {
    return null;
  }
}

export function saveQueueFilterSession(partial: QueueFilterSession): void {
  try {
    const prev = loadQueueFilterSession() || {};
    const next = { ...prev, ...partial };
    sessionStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* ignore quota / private mode */
  }
}
