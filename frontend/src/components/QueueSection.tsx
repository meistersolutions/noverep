import { useState } from 'react';
import { RefreshCw, SkipForward, Play, ListPlus, ListMusic } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { usePlayerStore } from '@/stores/playerStore';
import { formatDuration, QueueItem } from '@/lib/api';
import { AddToPlaylistModal } from '@/components/AddToPlaylistModal';

const TARGET = 20;

function QueueRow({
  item,
  index,
  isNowPlaying,
  onPlayNow,
  onPlayNext,
  onAddToPlaylist,
  onSkipToNext,
  playlistMode,
}: {
  item: QueueItem;
  index: number;
  isNowPlaying: boolean;
  onPlayNow: () => void;
  onPlayNext: () => void;
  onAddToPlaylist: () => void;
  onSkipToNext?: () => void;
  playlistMode: boolean;
}) {
  return (
    <li
      className={`glass p-3 flex items-center gap-3 ${
        isNowPlaying ? 'ring-2 ring-accent bg-accent/5' : ''
      }`}
    >
      <span className="text-white/40 w-6 text-center text-sm shrink-0">{index + 1}</span>
      {item.thumbnail_url ? (
        <img src={item.thumbnail_url} alt="" className="w-12 h-12 rounded object-cover shrink-0" />
      ) : (
        <div className="w-12 h-12 rounded bg-white/10 shrink-0" />
      )}
      <div className="flex-1 min-w-0">
        <p className="font-medium truncate text-sm">{item.title}</p>
        <p className="text-xs text-white/50 truncate">{item.artist}</p>
        <p className="text-[10px] text-white/40 mt-0.5">{formatDuration(item.duration_seconds)}</p>
      </div>
      <div className="flex flex-col sm:flex-row gap-1 shrink-0">
        <button
          type="button"
          className="btn-ghost text-xs px-2 py-1.5"
          onClick={onAddToPlaylist}
          title="Add to playlist"
        >
          <ListMusic className="w-3.5 h-3.5" />
        </button>
        {isNowPlaying ? (
          <span className="text-[10px] text-accent font-medium px-2 py-1">Now</span>
        ) : (
          <>
            {!playlistMode && (
              <button
                type="button"
                className="btn-ghost text-xs px-2 py-1.5 flex items-center gap-1"
                onClick={onPlayNext}
                title="Play next after current song"
              >
                <ListPlus className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Play Next</span>
              </button>
            )}
            <button
              type="button"
              className="btn-ghost text-xs px-2 py-1.5 flex items-center gap-1"
              onClick={onPlayNow}
              title="Play now"
            >
              <Play className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Play</span>
            </button>
          </>
        )}
        {onSkipToNext && (
          <button
            type="button"
            className="btn-primary text-xs px-2 py-1.5 flex items-center gap-1"
            onClick={onSkipToNext}
          >
            <SkipForward className="w-3.5 h-3.5" />
            Skip
          </button>
        )}
      </div>
    </li>
  );
}

interface QueueSectionProps {
  onRefreshPreferences: () => Promise<void>;
  refreshing?: boolean;
}

export function QueueSection({ onRefreshPreferences, refreshing = false }: QueueSectionProps) {
  const navigate = useNavigate();
  const { queue, refreshQueue, playTrack, playQueueItem, currentTrack, next, playbackMode } =
    usePlayerStore();
  const [playlistTrack, setPlaylistTrack] = useState<QueueItem | null>(null);
  const playlistMode = playbackMode === 'playlist';

  const currentIdx = queue.findIndex(
    (q) => q.is_current || q.provider_track_id === currentTrack?.provider_track_id,
  );
  const nowPlaying = currentIdx >= 0 ? queue[currentIdx] : currentTrack;
  const upNext = queue.filter((_, i) => i !== currentIdx);

  const handlePlayNow = async (item: QueueItem) => {
    try {
      if (playlistMode) {
        await playQueueItem(item);
      } else {
        await playTrack(item, true);
      }
      navigate('/now-playing');
    } catch {
      toast.error('Could not play');
    }
  };

  const handlePlayNextInsert = async (item: QueueItem) => {
    try {
      await usePlayerStore.getState().playNextInsert(item);
      toast.success(`"${item.title}" will play next`);
      await refreshQueue();
    } catch {
      toast.error('Could not queue');
    }
  };

  const handleSkip = async () => {
    await next();
    navigate('/now-playing');
  };

  const handleRefresh = async () => {
    await onRefreshPreferences();
    await refreshQueue();
  };

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h3 className="text-lg font-semibold">Queue</h3>
          <p className="text-sm text-white/50">
            {playlistMode
              ? `${queue.length} songs · playlist only`
              : `${queue.length} / ${TARGET} songs`}
          </p>
        </div>
        <div className="flex gap-2">
          {nowPlaying && (
            <button
              className="btn-primary flex items-center gap-1.5 text-sm py-2 px-3"
              onClick={handleSkip}
            >
              <SkipForward className="w-4 h-4" />
              Skip
            </button>
          )}
          {!playlistMode && (
            <button
              className="btn-ghost flex items-center gap-1.5 text-sm"
              onClick={handleRefresh}
              disabled={refreshing}
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          )}
        </div>
      </div>

      {playlistMode && (
        <p className="text-xs text-accent/80 bg-accent/10 px-3 py-2 rounded-lg">
          Playing from playlist — discovery is off. Play from Home or Search to return to discover mode.
        </p>
      )}

      {queue.length === 0 ? (
        <p className="text-white/50 text-sm">Queue is empty. Search or play a song to build your queue.</p>
      ) : (
        <>
          {nowPlaying && (
            <div>
              <h4 className="text-xs font-semibold text-white/60 mb-2 uppercase tracking-wide">
                Now Playing
              </h4>
              <ol className="space-y-2">
                <QueueRow
                  item={nowPlaying as QueueItem}
                  index={0}
                  isNowPlaying
                  playlistMode={playlistMode}
                  onPlayNow={() => {}}
                  onPlayNext={() => {}}
                  onAddToPlaylist={() => setPlaylistTrack(nowPlaying as QueueItem)}
                  onSkipToNext={handleSkip}
                />
              </ol>
            </div>
          )}

          <div>
            <h4 className="text-xs font-semibold text-white/60 mb-2 uppercase tracking-wide">
              Up Next ({upNext.length})
            </h4>
            {upNext.length === 0 ? (
              <p className="text-white/40 text-sm">No upcoming songs yet.</p>
            ) : (
              <ol className="space-y-2">
                {upNext.map((item, idx) => (
                  <QueueRow
                    key={item.id}
                    item={item}
                    index={idx + 1}
                    isNowPlaying={false}
                    playlistMode={playlistMode}
                    onPlayNow={() => handlePlayNow(item)}
                    onPlayNext={() => handlePlayNextInsert(item)}
                    onAddToPlaylist={() => setPlaylistTrack(item)}
                  />
                ))}
              </ol>
            )}
          </div>
        </>
      )}

      {playlistTrack && (
        <AddToPlaylistModal
          track={playlistTrack}
          open={!!playlistTrack}
          onClose={() => setPlaylistTrack(null)}
        />
      )}
    </section>
  );
}
