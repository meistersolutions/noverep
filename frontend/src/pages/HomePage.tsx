import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, RefreshCw } from 'lucide-react';
import toast from 'react-hot-toast';
import { Track } from '@/lib/api';
import { SongCard } from '@/components/SongCard';
import { MobileHeader } from '@/components/MobileHeader';
import { usePlayerStore } from '@/stores/playerStore';
import { useHomeStore } from '@/stores/homeStore';
import { useDiscoverOnly } from '@/components/DiscoverModeToggle';

export default function HomePage() {
  const navigate = useNavigate();
  const sections = useHomeStore((s) => s.sections);
  const loading = useHomeStore((s) => s.loading);
  const refreshing = useHomeStore((s) => s.refreshing);
  const loadHome = useHomeStore((s) => s.load);
  const playTrack = usePlayerStore((s) => s.playTrack);
  const playNextInsert = usePlayerStore((s) => s.playNextInsert);
  const queueTrack = usePlayerStore((s) => s.queueTrack);
  const preferences = usePlayerStore((s) => s.preferences);
  const discoverOnly = useDiscoverOnly();
  const displayName = preferences?.onboarding_completed
    ? localStorage.getItem('noverep_display_name')
    : null;

  useEffect(() => {
    // Show cached discovery immediately; refresh quietly in the background.
    void loadHome(false);
  }, [loadHome]);

  const handleRefresh = () => void loadHome(true);
  const busy = loading || refreshing;

  const handlePlay = async (track: Track) => {
    try {
      await playTrack(track, !discoverOnly);
      navigate('/now-playing');
    } catch {
      toast.error('Could not play this song');
    }
  };

  const handlePlayNext = async (track: Track) => {
    try {
      await playNextInsert(track, !discoverOnly);
      toast.success(`"${track.title}" will play next`);
    } catch {
      toast.error('Could not queue');
    }
  };

  const handleQueue = async (track: Track) => {
    try {
      await queueTrack(track, !discoverOnly);
      toast.success('Added to queue');
    } catch {
      toast.error('Could not add to queue');
    }
  };

  return (
    <div className="space-y-6 sm:space-y-8">
      <MobileHeader title="NoRepeat" showDiscoverToggle />

      <section className="glass p-5 sm:p-8 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-r from-accent/20 to-transparent" />
        <div className="relative">
          <h2 className="text-xl sm:text-3xl font-bold mb-2">
            {displayName ? `Hey ${displayName}` : 'Discover Without Repetition'}
          </h2>
          <p className="text-white/60 text-sm sm:text-base max-w-xl mb-4 sm:mb-6">
            Random surprises across your preferred languages — mixed artists, no repeats from blocked artists.
          </p>
          <button
            className="btn-primary flex items-center gap-2 text-sm sm:text-base"
            onClick={handleRefresh}
            disabled={busy}
          >
            <RefreshCw className={`w-4 h-4 ${busy ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          {refreshing && sections.length > 0 && (
            <p className="text-xs text-white/40 mt-2">Updating discovery in the background…</p>
          )}
        </div>
      </section>

      {loading && sections.length === 0 ? (
        <div className="grid gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="glass h-16 animate-pulse" />
          ))}
        </div>
      ) : sections.length === 0 ? (
        <p className="text-white/50 text-sm glass p-4 rounded-xl">
          No recommendations right now. Try refreshing, or use Search / Queue refresh to discover
          music.
        </p>
      ) : (
        sections.map((section) => (
          <section key={section.title}>
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="w-4 h-4 text-accent" />
              <h3 className="text-base sm:text-xl font-semibold">{section.title}</h3>
            </div>
            <div className="grid gap-2 sm:gap-3">
              {section.tracks.map((t) => (
                <SongCard
                  key={`${section.title}-${t.provider_track_id}`}
                  track={t}
                  onPlay={handlePlay}
                  onPlayNext={handlePlayNext}
                  onAdd={handleQueue}
                />
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
