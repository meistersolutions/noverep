import { Play, Plus, ListPlus } from 'lucide-react';
import { Track, formatDuration } from '@/lib/api';

interface SongCardProps {
  track: Track;
  onPlay: (track: Track) => void;
  onAdd?: (track: Track) => void;
  onPlayNext?: (track: Track) => void;
  showScore?: boolean;
  heard?: boolean;
}

export function SongCard({ track, onPlay, onAdd, onPlayNext, showScore, heard }: SongCardProps) {
  return (
    <div className="glass-hover p-3 flex items-center gap-3 sm:gap-4 group active:bg-white/5">
      <button
        type="button"
        onClick={() => onPlay(track)}
        className="relative w-14 h-14 sm:w-16 sm:h-16 shrink-0 touch-manipulation"
      >
        {track.thumbnail_url ? (
          <img
            src={track.thumbnail_url}
            alt=""
            className="w-full h-full rounded-lg object-cover"
          />
        ) : (
          <div className="w-full h-full rounded-lg bg-white/10" />
        )}
        <span className="absolute inset-0 flex items-center justify-center bg-black/40 rounded-lg md:opacity-0 md:group-hover:opacity-100 max-md:bg-black/30">
          <Play className="w-6 h-6 fill-white" />
        </span>
      </button>

      <button
        type="button"
        onClick={() => onPlay(track)}
        className="flex-1 min-w-0 text-left touch-manipulation"
      >
        <p className="font-medium truncate text-sm sm:text-base">{track.title}</p>
        <p className="text-xs sm:text-sm text-white/50 truncate">{track.artist}</p>
        <div className="flex flex-wrap items-center gap-1.5 mt-1 text-[10px] sm:text-xs text-white/40">
          <span>{formatDuration(track.duration_seconds)}</span>
          <span className="px-1.5 py-0.5 rounded bg-white/10 capitalize">{track.provider}</span>
          {heard && (
            <span className="px-1.5 py-0.5 rounded bg-yellow-500/20 text-yellow-300">Heard</span>
          )}
          {showScore && track.score != null && (
            <span className="text-accent hidden sm:inline">Score: {track.score.toFixed(1)}</span>
          )}
        </div>
      </button>

      <div className="flex flex-col gap-1 shrink-0">
        {onPlayNext && (
          <button
            type="button"
            className="btn-ghost touch-manipulation p-2"
            onClick={(e) => {
              e.stopPropagation();
              onPlayNext(track);
            }}
            aria-label="Play next"
            title="Play next"
          >
            <ListPlus className="w-5 h-5" />
          </button>
        )}
        {onAdd && (
          <button
            type="button"
            className="btn-ghost touch-manipulation p-2"
            onClick={(e) => {
              e.stopPropagation();
              onAdd(track);
            }}
            aria-label="Add to end of queue"
            title="Add to queue"
          >
            <Plus className="w-5 h-5" />
          </button>
        )}
      </div>
    </div>
  );
}

export function SongCardSkeleton() {
  return (
    <div className="glass p-3 flex items-center gap-3 animate-pulse">
      <div className="w-14 h-14 rounded-lg bg-white/10 shrink-0" />
      <div className="flex-1 space-y-2">
        <div className="h-4 bg-white/10 rounded w-3/4" />
        <div className="h-3 bg-white/10 rounded w-1/2" />
      </div>
    </div>
  );
}
