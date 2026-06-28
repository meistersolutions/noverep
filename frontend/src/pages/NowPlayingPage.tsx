import { useEffect, useState } from 'react';
import { usePlayerStore } from '@/stores/playerStore';
import { api, formatDuration, Track } from '@/lib/api';
import { Disc3, Pause, Play, ListMusic, ThumbsUp } from 'lucide-react';
import { AddToPlaylistModal } from '@/components/AddToPlaylistModal';
import toast from 'react-hot-toast';

export default function NowPlayingPage() {
  const currentTrack = usePlayerStore((s) => s.currentTrack);
  const isPlaying = usePlayerStore((s) => s.isPlaying);
  const currentTime = usePlayerStore((s) => s.currentTime);
  const duration = usePlayerStore((s) => s.duration);
  const setPlaying = usePlayerStore((s) => s.setPlaying);
  const queue = usePlayerStore((s) => s.queue);
  const playbackMode = usePlayerStore((s) => s.playbackMode);
  const [playlistOpen, setPlaylistOpen] = useState(false);
  const [liked, setLiked] = useState(false);
  const [liking, setLiking] = useState(false);

  const track =
    currentTrack ||
    queue.find((q) => q.is_current) ||
    (queue.length > 0 ? queue[queue.length - 1] : null);

  useEffect(() => {
    if (!track?.provider_track_id) {
      setLiked(false);
      return;
    }
    let cancelled = false;
    api
      .getLikedStatus(track.provider, track.provider_track_id)
      .then((res) => {
        if (!cancelled) setLiked(res.liked);
      })
      .catch(() => {
        if (!cancelled) setLiked(false);
      });
    return () => {
      cancelled = true;
    };
  }, [track?.provider, track?.provider_track_id]);

  const handleLike = async () => {
    if (!track || liking) return;
    setLiking(true);
    try {
      const res = await api.likeTrack(track.provider, track.provider_track_id, track);
      setLiked(true);
      toast.success(res.already_liked ? 'Already in Liked' : 'Added to Liked');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not like song');
    } finally {
      setLiking(false);
    }
  };

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

      <div className="flex items-center gap-3 mt-6">
        <button
          type="button"
          className={`btn-ghost p-3 rounded-full transition-colors ${
            liked ? 'text-accent bg-accent/15' : 'text-white/70'
          }`}
          onClick={handleLike}
          disabled={liking}
          aria-label={liked ? 'Liked' : 'Like song'}
          title={liked ? 'In Liked' : 'Add to Liked'}
        >
          <ThumbsUp className={`w-6 h-6 ${liked ? 'fill-current' : ''}`} />
        </button>
        <button
          className="btn-ghost flex items-center gap-2 px-4 py-2"
          onClick={() => setPlaylistOpen(true)}
        >
          <ListMusic className="w-5 h-5" />
          <span className="text-sm">Add to Playlist</span>
        </button>
        <button
          className="w-14 h-14 rounded-full bg-white text-black flex items-center justify-center hover:scale-105 transition-transform"
          onClick={() => setPlaying(!isPlaying)}
        >
          {isPlaying ? <Pause className="w-6 h-6" /> : <Play className="w-6 h-6 ml-0.5" />}
        </button>
      </div>

      <AddToPlaylistModal
        track={track as Track}
        open={playlistOpen}
        onClose={() => setPlaylistOpen(false)}
      />
    </div>
  );
}
