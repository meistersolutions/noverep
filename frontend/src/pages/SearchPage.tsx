import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ListMusic, Loader2, Search, X } from 'lucide-react';
import toast from 'react-hot-toast';
import { api, Track } from '@/lib/api';
import { SongCard, SongCardSkeleton } from '@/components/SongCard';
import { MobileHeader } from '@/components/MobileHeader';
import { DiscoverModeToggle, useDiscoverOnly } from '@/components/DiscoverModeToggle';
import { SearchPreferencesPanel } from '@/components/SearchPreferencesPanel';
import { QueueSection } from '@/components/QueueSection';
import { usePlayerStore } from '@/stores/playerStore';

export default function SearchPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Track[]>([]);
  const [searching, setSearching] = useState(false);
  const [queueUpdating, setQueueUpdating] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const playTrack = usePlayerStore((s) => s.playTrack);
  const queueTrack = usePlayerStore((s) => s.queueTrack);
  const playNextInsert = usePlayerStore((s) => s.playNextInsert);
  const refreshQueue = usePlayerStore((s) => s.refreshQueue);
  const refreshQueueFromSearch = usePlayerStore((s) => s.refreshQueueFromSearch);
  const refreshQueueFromPreferences = usePlayerStore((s) => s.refreshQueueFromPreferences);
  const clearActiveSearchQuery = usePlayerStore((s) => s.clearActiveSearchQuery);
  const queueBuilding = usePlayerStore((s) => s.queueBuilding);
  const preferences = usePlayerStore((s) => s.preferences);
  const activeSearch = preferences?.active_search_query;
  const discoverOnly = useDiscoverOnly();
  const includeHeard = !discoverOnly;

  useEffect(() => {
    if (preferences?.active_search_query) {
      setQuery(preferences.active_search_query);
    }
  }, [preferences?.active_search_query]);

  const handleQueryChange = async (value: string) => {
    setQuery(value);
    if (!value.trim() && activeSearch) {
      await clearActiveSearchQuery();
      toast.success('Queue will use random discovery again');
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    try {
      const res = await api.search(q, 'youtube', includeHeard, true);
      setResults(res.results);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setSearching(false);
    }
  };

  const handleUpdateQueue = async () => {
    const q = query.trim();
    if (!q) {
      toast.error('Enter a search term first');
      return;
    }
    if (usePlayerStore.getState().playbackMode === 'playlist') {
      toast.error('Exit playlist mode first — play from Home or Search');
      return;
    }
    setQueueUpdating(true);
    toast('Building your queue in the background…', { icon: '⏳' });
    try {
      await refreshQueueFromSearch(q);
      await refreshQueue();
      toast.success('Queue updated from your search');
    } catch {
      toast.error('Could not update queue');
    } finally {
      setQueueUpdating(false);
    }
  };

  const handleClearSearch = async () => {
    setQuery('');
    setResults([]);
    if (activeSearch) {
      await clearActiveSearchQuery();
      toast.success('Queue will use random discovery again');
    }
  };

  const handleRefreshPreferences = async () => {
    setRefreshing(true);
    toast('Refreshing queue from preferences in the background…', { icon: '⏳' });
    try {
      await refreshQueueFromPreferences();
      setQuery('');
      setResults([]);
      await refreshQueue();
      toast.success('Queue refreshed from your preferences');
    } catch {
      toast.error('Could not refresh queue');
    } finally {
      setRefreshing(false);
    }
  };

  const handlePlay = async (track: Track) => {
    try {
      await playTrack(track, includeHeard);
      navigate('/now-playing');
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : 'Cannot play — song was heard recently. Toggle "All songs" to replay.',
      );
    }
  };

  const handlePlayNext = async (track: Track) => {
    try {
      await playNextInsert(track, includeHeard);
      toast.success(`"${track.title}" will play next`);
      await refreshQueue();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not queue');
    }
  };

  const handleAddToQueue = async (track: Track) => {
    try {
      await queueTrack(track, includeHeard);
      toast.success('Added to queue');
      await refreshQueue();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not add to queue');
    }
  };

  return (
    <div className="space-y-6 max-w-3xl pb-4">
      <MobileHeader title="Search & Queue" showDiscoverToggle />
      <h2 className="hidden md:block text-2xl font-bold">Search & Queue</h2>

      <div className="hidden md:block">
        <DiscoverModeToggle />
      </div>

      {queueBuilding && (
        <p className="text-xs text-accent/90 flex items-center gap-2 glass px-3 py-2 rounded-lg">
          <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
          Building your discovery queue in the background — you can search and play right away.
        </p>
      )}

      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-white/40 pointer-events-none" />
          <input
            type="search"
            enterKeyHint="search"
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            placeholder="Search songs, artists…"
            className="w-full glass pl-12 pr-10 py-3.5 text-base focus:outline-none focus:ring-2 focus:ring-accent/50"
          />
          {query && (
            <button
              type="button"
              onClick={handleClearSearch}
              className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-white/40 hover:text-white"
              aria-label="Clear search"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>
        <button
          type="submit"
          disabled={searching || !query.trim()}
          className="btn-primary px-4 shrink-0 flex items-center gap-2"
        >
          {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          <span className="hidden sm:inline">Search</span>
        </button>
        <button
          type="button"
          onClick={handleUpdateQueue}
          disabled={queueUpdating || !query.trim()}
          className="btn-ghost px-3 shrink-0 flex items-center gap-2 border border-white/10"
          title="Rebuild upcoming queue from this search (runs in background)"
        >
          {queueUpdating ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <ListMusic className="w-4 h-4" />
          )}
          <span className="hidden sm:inline">Update Queue</span>
        </button>
      </form>

      <p className="text-xs text-white/40">
        <strong className="text-white/60">Search</strong> shows results instantly. Use{' '}
        <strong className="text-white/60">Update Queue</strong> when you want upcoming tracks rebuilt
        from your query (works in the background).
      </p>

      {activeSearch && (
        <p className="text-xs text-accent/90">
          Queue seed: <span className="font-medium">&ldquo;{activeSearch}&rdquo;</span> — clear search
          to return to random discovery.
        </p>
      )}

      <SearchPreferencesPanel
        onPreferencesSaved={() => {
          if (!activeSearch) {
            void refreshQueueFromPreferences();
          }
        }}
      />

      <QueueSection onRefreshPreferences={handleRefreshPreferences} refreshing={refreshing} />

      {results.length > 0 || searching ? (
        <section className="space-y-3">
          <h3 className="text-lg font-semibold">Results</h3>
          <div className="grid gap-2 sm:gap-3">
            {searching && Array.from({ length: 5 }).map((_, i) => <SongCardSkeleton key={i} />)}
            {!searching &&
              results.map((t) => (
                <SongCard
                  key={t.provider_track_id}
                  track={t}
                  onPlay={handlePlay}
                  onPlayNext={handlePlayNext}
                  onAdd={handleAddToQueue}
                />
              ))}
            {!searching && results.length === 0 && query && (
              <p className="text-white/50 text-center py-8">No songs found. Try another search.</p>
            )}
          </div>
        </section>
      ) : null}
    </div>
  );
}
