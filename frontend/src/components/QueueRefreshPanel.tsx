import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { ChevronDown, ChevronUp, Filter, Loader2, Plus, RefreshCw, X } from 'lucide-react';
import { LanguageMultiSelect } from '@/components/LanguageMultiSelect';
import { DiscoveryYearRangeInput } from '@/components/DiscoveryYearRangeInput';
import { effectiveLanguages } from '@/lib/languages';
import { api } from '@/lib/api';
import { usePlayerStore } from '@/stores/playerStore';
import type { QueueRefreshOptions } from '@/lib/api';

const MAX_SEEDS = 5;

interface QueueRefreshPanelProps {
  seeds: string[];
  onSeedsChange: (seeds: string[]) => void;
  onRefresh: (seeds: string[] | null, options: QueueRefreshOptions) => Promise<void>;
  refreshing?: boolean;
}

function normalizeSeedList(seeds: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of seeds) {
    const q = raw.trim();
    if (!q) continue;
    const key = q.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(q);
    if (out.length >= MAX_SEEDS) break;
  }
  return out;
}

export function QueueRefreshPanel({
  seeds,
  onSeedsChange,
  onRefresh,
  refreshing = false,
}: QueueRefreshPanelProps) {
  const preferences = usePlayerStore((s) => s.preferences);
  const activeSeedKey = (
    preferences?.active_search_queries?.length
      ? preferences.active_search_queries
      : preferences?.active_search_query
        ? [preferences.active_search_query]
        : []
  ).join('\0');
  const [draft, setDraft] = useState('');
  const [open, setOpen] = useState(true);
  const [languages, setLanguages] = useState<string[]>([]);
  const [yearFrom, setYearFrom] = useState<number | null>(null);
  const [yearTo, setYearTo] = useState<number | null>(null);
  const [youtubeDiscovery, setYoutubeDiscovery] = useState(true);
  const lastHydratedKey = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (!preferences) return;
    setLanguages(effectiveLanguages(preferences.preferred_languages, preferences.language_preference));
    setYearFrom(preferences.discovery_year_from);
    setYearTo(preferences.discovery_year_to);
    setYoutubeDiscovery(preferences.discovery_youtube_enabled ?? true);
  }, [preferences]);

  // Hydrate chips when saved seeds change — do NOT re-fill after the user clears them.
  useEffect(() => {
    if (activeSeedKey === lastHydratedKey.current) return;
    lastHydratedKey.current = activeSeedKey;
    const next = activeSeedKey ? activeSeedKey.split('\0') : [];
    if (next.length) onSeedsChange(next);
  }, [activeSeedKey, onSeedsChange]);

  const buildOptions = (): QueueRefreshOptions => ({
    languages,
    yearFrom,
    yearTo,
  });

  const addSeed = (raw: string) => {
    const next = normalizeSeedList([...seeds, raw]);
    onSeedsChange(next);
    setDraft('');
  };

  const removeSeed = (seed: string) => {
    onSeedsChange(seeds.filter((s) => s.toLowerCase() !== seed.toLowerCase()));
  };

  const handleDraftKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (draft.trim()) addSeed(draft);
    }
  };

  const handleRefresh = async () => {
    const pending = draft.trim() ? normalizeSeedList([...seeds, draft]) : seeds;
    if (draft.trim()) {
      onSeedsChange(pending);
      setDraft('');
    }
    await onRefresh(pending.length ? pending : null, buildOptions());
  };

  const toggleYoutubeDiscovery = async () => {
    const next = !youtubeDiscovery;
    setYoutubeDiscovery(next);
    try {
      const updated = await api.updatePreferences({ discovery_youtube_enabled: next });
      usePlayerStore.setState({ preferences: updated });
    } catch {
      setYoutubeDiscovery(!next);
    }
  };

  if (!preferences) {
    return <div className="glass h-32 animate-pulse rounded-xl" />;
  }

  return (
    <section className="glass overflow-hidden space-y-0">
      <div className="p-4 space-y-3 border-b border-white/10">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <label className="text-sm font-medium">Queue seeds (optional)</label>
          <button
            type="button"
            onClick={toggleYoutubeDiscovery}
            className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
              youtubeDiscovery
                ? 'border-accent/50 bg-accent/15 text-accent'
                : 'border-white/15 bg-white/5 text-white/70'
            }`}
            title={
              youtubeDiscovery
                ? 'YouTube discovery is on — queue mixes library + YouTube search'
                : 'Library only — songs from Songs Library; YouTube used only to play'
            }
          >
            {youtubeDiscovery ? 'YouTube discovery: ON' : 'YouTube discovery: OFF (library only)'}
          </button>
        </div>
        <p className="text-xs text-white/50">
          Add up to {MAX_SEEDS} searches. We rotate across them to mix niches into your queue. Leave
          empty to refresh from your saved preferences.
          {youtubeDiscovery
            ? ' Home discovery can fill gaps when the queue runs dry.'
            : ' With YouTube discovery off, only the Songs Library catalog is used; YouTube is still used to play tracks.'}
        </p>

        {seeds.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {seeds.map((seed) => (
              <span
                key={seed}
                className="inline-flex items-center gap-1 rounded-lg bg-white/10 px-2.5 py-1 text-sm"
              >
                {seed}
                <button
                  type="button"
                  onClick={() => removeSeed(seed)}
                  className="p-0.5 rounded text-white/50 hover:text-white hover:bg-white/10"
                  aria-label={`Remove seed ${seed}`}
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </span>
            ))}
          </div>
        )}

        <div className="flex gap-2">
          <div className="relative flex-1 min-w-0">
            <input
              type="text"
              inputMode="search"
              enterKeyHint="done"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={handleDraftKey}
              disabled={seeds.length >= MAX_SEEDS}
              placeholder={
                seeds.length >= MAX_SEEDS
                  ? `Maximum ${MAX_SEEDS} seeds`
                  : 'e.g. Ilaiyaraaja, coldplay…'
              }
              className="w-full bg-surface-raised border border-white/10 rounded-lg px-4 py-2.5 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-accent/50 disabled:opacity-50"
            />
            {draft ? (
              <button
                type="button"
                onClick={() => setDraft('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-md text-white/50 hover:text-white hover:bg-white/10"
                aria-label="Clear draft"
              >
                <X className="w-4 h-4" />
              </button>
            ) : null}
          </div>
          <button
            type="button"
            onClick={() => draft.trim() && addSeed(draft)}
            disabled={!draft.trim() || seeds.length >= MAX_SEEDS}
            className="btn-ghost px-3 shrink-0 flex items-center gap-1.5 text-sm border border-white/10 disabled:opacity-40"
            aria-label="Add seed"
          >
            <Plus className="w-4 h-4" />
            <span className="hidden sm:inline">Add</span>
          </button>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={refreshing}
            className="btn-primary px-4 shrink-0 flex items-center gap-2 text-sm"
          >
            {refreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            <span className="hidden sm:inline">Refresh queue</span>
          </button>
        </div>
        {activeSeedKey && (
          <p className="text-xs text-accent/90">
            Active seeds:{' '}
            <span className="font-medium">
              {activeSeedKey
                .split('\0')
                .map((s) => `"${s}"`)
                .join(', ')}
            </span>
          </p>
        )}
      </div>

      <button
        type="button"
        className="w-full flex items-center justify-between gap-3 p-4 text-left hover:bg-white/5 transition-colors"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <div className="flex items-center gap-2">
          <Filter className="w-5 h-5 text-accent shrink-0" />
          <div>
            <p className="font-semibold text-sm">Discovery filters</p>
            <p className="text-xs text-white/50">Languages and year range for queue refresh</p>
          </div>
        </div>
        {open ? (
          <ChevronUp className="w-5 h-5 text-white/40 shrink-0" />
        ) : (
          <ChevronDown className="w-5 h-5 text-white/40 shrink-0" />
        )}
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-5 border-t border-white/10 pt-4">
          <div className="space-y-2">
            <p className="text-sm font-medium">Languages</p>
            <LanguageMultiSelect compact selected={languages} onChange={setLanguages} />
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium">Year range</p>
            <DiscoveryYearRangeInput
              compact
              yearFrom={yearFrom}
              yearTo={yearTo}
              onSave={(from, to) => {
                setYearFrom(from);
                setYearTo(to);
              }}
            />
          </div>
        </div>
      )}
    </section>
  );
}
