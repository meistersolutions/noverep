import { useEffect, useState } from 'react';
import { ListMusic, ThumbsUp } from 'lucide-react';
import toast from 'react-hot-toast';
import { api, Track } from '@/lib/api';
import { AddToPlaylistModal } from '@/components/AddToPlaylistModal';

interface TrackPlayerActionsProps {
  track: Track;
  compact?: boolean;
}

export function TrackPlayerActions({ track, compact = false }: TrackPlayerActionsProps) {
  const [liked, setLiked] = useState(false);
  const [liking, setLiking] = useState(false);
  const [playlistOpen, setPlaylistOpen] = useState(false);

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
    if (liking) return;
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

  const btnClass = compact
    ? 'btn-ghost p-2 rounded-full'
    : 'btn-ghost p-2.5 rounded-full';

  return (
    <>
      <button
        type="button"
        className={`${btnClass} ${liked ? 'text-accent bg-accent/15' : 'text-white/70'}`}
        onClick={handleLike}
        disabled={liking}
        aria-label={liked ? 'Liked' : 'Like song'}
        title={liked ? 'In Liked' : 'Add to Liked'}
      >
        <ThumbsUp className={`w-5 h-5 ${liked ? 'fill-current' : ''}`} />
      </button>
      <button
        type="button"
        className={`${btnClass} text-white/70`}
        onClick={() => setPlaylistOpen(true)}
        aria-label="Add to playlist"
        title="Add to playlist"
      >
        <ListMusic className="w-5 h-5" />
      </button>
      <AddToPlaylistModal track={track} open={playlistOpen} onClose={() => setPlaylistOpen(false)} />
    </>
  );
}
