import { useEffect } from 'react';
import { usePlayerStore } from '@/stores/playerStore';
import { formatDuration, Track } from '@/lib/api';
import { Disc3, Pause, Play } from 'lucide-react';
import { TrackPlayerActions } from '@/components/TrackPlayerActions';
import { SongDetailsPanel } from '@/components/SongDetailsPanel';
import { LyricsPanel } from '@/components/LyricsPanel';

export default function NowPlayingPage() {
  const currentTrack = usePlayerStore((s) => s.currentTrack);
  const isPlaying = usePlayerStore((s) => s.isPlaying);
  const currentTime = usePlayerStore((s) => s.currentTime);
  const duration = usePlayerStore((s) => s.duration);
  const setPlaying = usePlayerStore((s) => s.setPlaying);
  const playbackMode = usePlayerStore((s) => s.playbackMode);
  const syncFromPlayer = usePlayerStore((s) => s.syncFromPlayer);

  useEffect(() => {
    syncFromPlayer();
  }, [syncFromPlayer, currentTrack?.provider_track_id]);

  const track = currentTrack;

  if (!track) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-white/50">
        <Disc3 className="w-16 h-16 mb-4 opacity-30" />
        <p className="text-xl">Nothing playing</p>
        <p className="text-sm mt-2">Search for music or pick a recommendation to start</p>
      </div>
    );
  }

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div className="flex flex-col items-center max-w-lg mx-auto pt-8">
      {playbackMode === 'playlist' && (
        <p className="text-xs text-accent mb-4 px-3 py-1 rounded-full bg-accent/10">
          Playlist mode — no discovery
        </p>
      )}

      <div className="relative mb-8">
        {track.thumbnail_url ? (
          <img
            src={track.thumbnail_url}
            alt=""
            className={`w-80 h-80 rounded-2xl object-cover shadow-2xl shadow-accent/20 ${isPlaying ? 'animate-pulse-slow' : ''}`}
          />
        ) : (
          <div className="w-80 h-80 rounded-2xl bg-white/10 flex items-center justify-center">
            <Disc3 className="w-24 h-24 text-white/20" />
          </div>
        )}
      </div>

      <h2 className="text-3xl font-bold text-center px-4">{track.title}</h2>
      <p className="text-xl text-white/60 mt-2">{track.artist}</p>
      {track.album && <p className="text-sm text-white/40 mt-1">{track.album}</p>}

      <div className="flex items-center gap-4 mt-4 text-sm text-white/50">
        <span className="capitalize px-2 py-0.5 rounded bg-white/10">{track.provider}</span>
        {isPlaying && <span className="text-accent">Now Playing</span>}
      </div>

      <div className="w-full max-w-md mt-8 space-y-2">
        <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
          <div
            className="h-full bg-accent transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-white/50">
          <span>{formatDuration(Math.floor(currentTime))}</span>
          <span>{formatDuration(Math.floor(duration))}</span>
        </div>
      </div>

      <div className="flex items-center gap-4 mt-6">
        <TrackPlayerActions track={track as Track} />
        <button
          className="w-14 h-14 rounded-full bg-white text-black flex items-center justify-center hover:scale-105 transition-transform"
          onClick={() => setPlaying(!isPlaying)}
        >
          {isPlaying ? <Pause className="w-6 h-6" /> : <Play className="w-6 h-6 ml-0.5" />}
        </button>
      </div>

      <SongDetailsPanel
        provider={track.provider}
        providerTrackId={track.provider_track_id}
        title={track.title}
        artist={track.artist}
      />
      <LyricsPanel track={track as Track} />
    </div>
  );
}
