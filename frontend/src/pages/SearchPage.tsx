import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, X } from 'lucide-react';
import toast from 'react-hot-toast';
import { api, Track } from '@/lib/api';
import { SongCard, SongCardSkeleton } from '@/components/SongCard';
import { MobileHeader } from '@/components/MobileHeader';
import { DiscoverModeToggle, useDiscoverOnly } from '@/components/DiscoverModeToggle';
import { QueueSection } from '@/components/QueueSection';
import { usePlayerStore } from '@/stores/playerStore';

export default function SearchPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Track[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const playTrack = usePlayerStore((s) => s.playTrack);
  const queueTrack = usePlayerStore((s) => s.queueTrack);
  const playNextInsert = usePlayerStore((s) => s.playNextInsert);
  const refreshQueue = usePlayerStore((s) => s.refreshQueue);
  const refreshQueueFromSearch = usePlayerStore((s) => s.refreshQueueFromSearch);
  const refreshQueueFromPreferences = usePlayerStore((s) => s.refreshQueueFromPreferences);
  const clearActiveSearchQuery = usePlayerStore((s) => s.clearActiveSearchQuery);
  const preferences = usePlayerStore((s) => s.preferences);
  const activeSearch = preferences?.active_search_query;
  const discoverOnly = useDiscoverOnly();
  const includeHeard = !discoverOnly;

  useEffect(() => {
    refreshQueue();
  }, [refreshQueue]);

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
    if (usePlayerStore.getState().playbackMode === 'playlist') {
      toast.error('Exit playlist mode first — play from Home or Search');
      return;
    }
    setLoading(true);
    try {
      const [res] = await Promise.all([
        api.search(q, 'youtube', includeHeard),
        refreshQueueFromSearch(q),
      ]);
      setResults(res.results);
      await refreshQueue();
      toast.success('Queue locked to your search');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setLoading(false);
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
    try {
      await refreshQueueFromPreferences();
      setQuery('');
      setResults([]);
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

      <form onSubmit={handleSearch} className="relative">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-white/40 pointer-events-none" />
        <input
          type="search"
          enterKeyHint="search"
          value={query}
          onChange={(e) => handleQueryChange(e.target.value)}
          placeholder="Search songs, artists..."
          className="w-full glass pl-12 pr-12 py-3.5 text-base focus:outline-none focus:ring-2 focus:ring-accent/50"
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
      </form>

      {activeSearch && (
        <p className="text-xs text-accent/90">
          Queue is building from: <span className="font-medium">&ldquo;{activeSearch}&rdquo;</span> — clear
          search to return to random discovery.
        </p>
      )}

      <p className="text-xs text-white/40">
        {discoverOnly
          ? 'Discover mode: hiding songs you heard recently. Search locks the queue to your query.'
          : 'All songs mode. Search locks upcoming queue tracks to your query until cleared.'}
      </p>

      <QueueSection onRefreshPreferences={handleRefreshPreferences} refreshing={refreshing} />

      {results.length > 0 || loading ? (
        <section className="space-y-3">
          <h3 className="text-lg font-semibold">Results</h3>
          <div className="grid gap-2 sm:gap-3">
            {loading && Array.from({ length: 5 }).map((_, i) => <SongCardSkeleton key={i} />)}
            {!loading &&
              results.map((t) => (
                <SongCard
                  key={t.provider_track_id}
                  track={t}
                  onPlay={handlePlay}
                  onPlayNext={handlePlayNext}
                  onAdd={handleAddToQueue}
                />
              ))}
            {!loading && results.length === 0 && query && (
              <p className="text-white/50 text-center py-8">No songs found. Try another search.</p>
            )}
          </div>
        </section>
      ) : null}
    </div>
  );
}
