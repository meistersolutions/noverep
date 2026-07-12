/** Local set of heard YouTube ids — filters session-cached queue before server sync. */

const HEARD_KEY = 'noverep_heard_track_ids';
const MAX_IDS = 2000;

function readIds(): string[] {
  try {
    const raw = localStorage.getItem(HEARD_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((id) => typeof id === 'string') : [];
  } catch {
    return [];
  }
}

function writeIds(ids: string[]): void {
  try {
    localStorage.setItem(HEARD_KEY, JSON.stringify(ids.slice(0, MAX_IDS)));
  } catch {
    /* ignore */
  }
}

export function markTrackHeardLocally(providerTrackId: string): void {
  if (!providerTrackId) return;
  const ids = readIds().filter((id) => id !== providerTrackId);
  ids.unshift(providerTrackId);
  writeIds(ids);
}

export function getHeardTrackIdSet(): Set<string> {
  return new Set(readIds());
}

export function syncHeardFromHistory(
  entries: Array<{ provider_track_id?: string | null }>,
): void {
  const incoming = entries
    .map((e) => e.provider_track_id)
    .filter((id): id is string => !!id);
  if (!incoming.length) return;
  const merged = [...incoming, ...readIds().filter((id) => !incoming.includes(id))];
  writeIds(merged);
}

export function filterQueueAgainstHeard<
  T extends { provider_track_id: string; is_current?: boolean },
>(queue: T[], keepProviderTrackId?: string | null): T[] {
  const heard = getHeardTrackIdSet();
  if (!heard.size) return queue;
  return queue.filter(
    (item) =>
      item.is_current ||
      item.provider_track_id === keepProviderTrackId ||
      !heard.has(item.provider_track_id),
  );
}

export function clearHeardTrackCache(): void {
  try {
    localStorage.removeItem(HEARD_KEY);
  } catch {
    /* ignore */
  }
}
