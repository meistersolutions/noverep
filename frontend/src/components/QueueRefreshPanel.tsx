import { useEffect, useState } from 'react';
import { ChevronDown, ChevronUp, Filter, Loader2, RefreshCw } from 'lucide-react';
import toast from 'react-hot-toast';
import { LanguageMultiSelect } from '@/components/LanguageMultiSelect';
import { DiscoveryYearRangeInput } from '@/components/DiscoveryYearRangeInput';
import { effectiveLanguages } from '@/lib/languages';
import { usePlayerStore } from '@/stores/playerStore';
import type { QueueRefreshOptions } from '@/lib/api';

interface QueueRefreshPanelProps {
  query: string;
  onQueryChange: (value: string) => void;
  onRefreshFromQuery: (query: string, options: QueueRefreshOptions) => Promise<void>;
  onRefreshFromPreferences: (options: QueueRefreshOptions) => Promise<void>;
  refreshing?: boolean;
}

export function QueueRefreshPanel({
  query,
  onQueryChange,
  onRefreshFromQuery,
  onRefreshFromPreferences,
  refreshing = false,
}: QueueRefreshPanelProps) {
  const preferences = usePlayerStore((s) => s.preferences);
  const activeSearch = preferences?.active_search_query;
  const [open, setOpen] = useState(true);
  const [languages, setLanguages] = useState<string[]>([]);
  const [yearFrom, setYearFrom] = useState<number | null>(null);
  const [yearTo, setYearTo] = useState<number | null>(null);
  const [includeHeard, setIncludeHeard] = useState(false);

  useEffect(() => {
    if (!preferences) return;
    setLanguages(effectiveLanguages(preferences.preferred_languages, preferences.language_preference));
    setYearFrom(preferences.discovery_year_from);
    setYearTo(preferences.discovery_year_to);
    setIncludeHeard(!preferences.repeat_disabled);
  }, [preferences]);

  useEffect(() => {
    if (activeSearch && !query) {
      onQueryChange(activeSearch);
    }
  }, [activeSearch, onQueryChange, query]);

  const buildOptions = (): QueueRefreshOptions => ({
    languages,
    yearFrom,
    yearTo,
    includeHeard,
  });

  const handleRefreshQuery = async () => {
    const q = query.trim();
    if (!q) {
      toast.error('Enter a query to seed the queue');
      return;
    }
    await onRefreshFromQuery(q, buildOptions());
  };

  const handleRefreshPreferences = async () => {
    await onRefreshFromPreferences(buildOptions());
  };

  if (!preferences) {
    return <div className="glass h-32 animate-pulse rounded-xl" />;
  }

  return (
    <section className="glass overflow-hidden space-y-0">
      <div className="p-4 space-y-3 border-b border-white/10">
        <label className="text-sm font-medium">Queue seed query</label>
        <p className="text-xs text-white/50">
          Rebuild upcoming tracks from this search. Leave empty and use &ldquo;Refresh from preferences&rdquo;
          for random discovery.
        </p>
        <div className="flex gap-2">
          <input
            type="search"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="e.g. Ilaiyaraaja, rock 90s, AR Rahman…"
            className="flex-1 bg-surface-raised border border-white/10 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent/50"
          />
          <button
            type="button"
            onClick={handleRefreshQuery}
            disabled={refreshing || !query.trim()}
            className="btn-primary px-4 shrink-0 flex items-center gap-2 text-sm"
          >
            {refreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            <span className="hidden sm:inline">Refresh</span>
          </button>
        </div>
        {activeSearch && (
          <p className="text-xs text-accent/90">
            Active seed: <span className="font-medium">&ldquo;{activeSearch}&rdquo;</span>
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
            <p className="font-semibold text-sm">Discovery filters for this refresh</p>
            <p className="text-xs text-white/50">Applied when you refresh — not used for instant search</p>
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

          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={includeHeard}
              onChange={(e) => setIncludeHeard(e.target.checked)}
              className="accent-accent w-4 h-4"
            />
            <div>
              <span className="text-sm font-medium">Include heard songs</span>
              <p className="text-xs text-white/50">Allow songs from your listening history in the queue</p>
            </div>
          </label>

          <button
            type="button"
            onClick={handleRefreshPreferences}
            disabled={refreshing}
            className="btn-ghost w-full flex items-center justify-center gap-2 border border-white/10 text-sm py-2.5"
          >
            {refreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            Refresh from saved preferences
          </button>
        </div>
      )}
    </section>
  );
}
