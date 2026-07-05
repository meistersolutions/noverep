import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Loader2, Search, Video, X } from 'lucide-react';
import toast from 'react-hot-toast';
import { api, Track } from '@/lib/api';
import { SongCard, SongCardSkeleton } from '@/components/SongCard';
import { MobileHeader } from '@/components/MobileHeader';
import { DiscoverModeToggle, useDiscoverOnly } from '@/components/DiscoverModeToggle';
import { usePlayerStore } from '@/stores/playerStore';

const ANY_VIDEO_KEY = 'noverep_search_any_video';

export default function SearchPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Track[]>([]);
  const [searching, setSearching] = useState(false);
  const [anyVideo, setAnyVideo] = useState(
    () => localStorage.getItem(ANY_VIDEO_KEY) === 'true',
  );
  const playTrack = usePlayerStore((s) => s.playTrack);
  const queueTrack = usePlayerStore((s) => s.queueTrack);
  const playNextInsert = usePlayerStore((s) => s.playNextInsert);
  const refreshQueue = usePlayerStore((s) => s.refreshQueue);
  const discoverOnly = useDiscoverOnly();
  const includeHeard = !discoverOnly;

  const toggleAnyVideo = () => {
    setAnyVideo((prev) => {
      const next = !prev;
      localStorage.setItem(ANY_VIDEO_KEY, String(next));
      return next;
    });
    setResults([]);
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    try {
      const res = await api.search(q, 'youtube', includeHeard, true, true, anyVideo);
      setResults(res.results);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setSearching(false);
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
      <MobileHeader title="Search" showDiscoverToggle />
      <h2 className="hidden md:block text-2xl font-bold">Search</h2>

      <div className="hidden md:block">
        <DiscoverModeToggle />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          role="switch"
          aria-checked={anyVideo}
          onClick={toggleAnyVideo}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors border ${
            anyVideo
              ? 'bg-accent/20 border-accent/40 text-accent-hover'
              : 'bg-white/5 border-white/10 text-white/70 hover:text-white'
          }`}
        >
          <Video className="w-4 h-4 shrink-0" />
          <span>Any YouTube video (audio only)</span>
        </button>
      </div>

      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-white/40 pointer-events-none" />
          <input
            type="search"
            enterKeyHint="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={anyVideo ? 'Search any YouTube video…' : 'Search songs, artists…'}
            className="w-full glass pl-12 pr-10 py-3.5 text-base focus:outline-none focus:ring-2 focus:ring-accent/50"
          />
          {query && (
            <button
              type="button"
              onClick={() => {
                setQuery('');
                setResults([]);
              }}
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
      </form>

      <p className="text-xs text-white/40">
        {anyVideo
          ? 'Searches all YouTube videos and plays audio in the background — podcasts, talks, lectures, and more.'
          : 'Single songs only (no playlists or concerts). Language and discovery preferences apply on the'}{' '}
        {!anyVideo && (
          <Link to="/queue" className="text-accent hover:underline">
            Queue
          </Link>
        )}
        {!anyVideo && ' page.'}
      </p>

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
              <p className="text-white/50 text-center py-8">
                {anyVideo ? 'No videos found. Try another search.' : 'No songs found. Try another search.'}
              </p>
            )}
          </div>
        </section>
      ) : null}
    </div>
  );
}
