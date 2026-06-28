import { Play, Pause, SkipBack, SkipForward } from 'lucide-react';
import { usePlayerStore } from '@/stores/playerStore';
import { seekPlayback } from '@/lib/youtubePlayerController';
import { formatDuration } from '@/lib/api';
import { Link } from 'react-router-dom';

export function PlayerBar() {
  const {
    currentTrack,
    isPlaying,
    currentTime,
    duration,
    setPlaying,
    next,
    previous,
  } = usePlayerStore();

  if (!currentTrack) return null;

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <footer className="fixed bottom-0 left-0 right-0 glass border-t border-white/10 z-50 safe-bottom">
      {/* Progress line */}
      <div
        className="absolute top-0 left-0 h-0.5 bg-accent transition-all"
        style={{ width: `${progress}%` }}
      />

      {/* Mobile layout */}
      <div className="md:hidden px-3 py-2 space-y-2">
        <div className="flex items-center gap-3">
          <Link to="/now-playing" className="flex items-center gap-3 min-w-0 flex-1">
            {currentTrack.thumbnail_url ? (
              <img
                src={currentTrack.thumbnail_url}
                alt=""
                className="w-11 h-11 rounded-lg object-cover shrink-0"
              />
            ) : (
              <div className="w-11 h-11 rounded-lg bg-white/10 shrink-0" />
            )}
            <div className="min-w-0">
              <p className="font-medium truncate text-sm">{currentTrack.title}</p>
              <p className="text-xs text-white/50 truncate">{currentTrack.artist}</p>
            </div>
          </Link>
          <div className="flex items-center gap-1 shrink-0">
            <button className="btn-ghost p-2" onClick={() => previous()} aria-label="Previous">
              <SkipBack className="w-5 h-5" />
            </button>
            <button
              className="w-10 h-10 rounded-full bg-white text-black flex items-center justify-center"
              onClick={() => setPlaying(!isPlaying)}
              aria-label={isPlaying ? 'Pause' : 'Play'}
            >
              {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
            </button>
            <button className="btn-ghost p-2" onClick={() => next()} aria-label="Next">
              <SkipForward className="w-5 h-5" />
            </button>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-white/50 w-8">
            {formatDuration(Math.floor(currentTime))}
          </span>
          <input
            type="range"
            min={0}
            max={duration || 100}
            value={currentTime}
            onChange={(e) => seekPlayback(Number(e.target.value))}
            className="flex-1 h-1 accent-accent"
          />
          <span className="text-[10px] text-white/50 w-8 text-right">
            {formatDuration(Math.floor(duration))}
          </span>
        </div>
      </div>

      {/* Desktop layout */}
      <div className="hidden md:block px-4 py-3">
        <div className="max-w-screen-2xl mx-auto flex items-center gap-4">
          <Link to="/now-playing" className="flex items-center gap-3 min-w-0 w-64 shrink-0">
            {currentTrack.thumbnail_url ? (
              <img
                src={currentTrack.thumbnail_url}
                alt=""
                className="w-14 h-14 rounded-lg object-cover"
              />
            ) : (
              <div className="w-14 h-14 rounded-lg bg-white/10" />
            )}
            <div className="min-w-0">
              <p className="font-medium truncate text-sm">{currentTrack.title}</p>
              <p className="text-xs text-white/50 truncate">{currentTrack.artist}</p>
            </div>
          </Link>

          <div className="flex-1 flex flex-col items-center gap-2 max-w-xl mx-auto">
            <div className="flex items-center gap-4">
              <button className="btn-ghost" onClick={() => previous()} aria-label="Previous">
                <SkipBack className="w-5 h-5" />
              </button>
              <button
                className="w-10 h-10 rounded-full bg-white text-black flex items-center justify-center hover:scale-105 transition-transform"
                onClick={() => setPlaying(!isPlaying)}
              >
                {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
              </button>
              <button className="btn-ghost" onClick={() => next()} aria-label="Next">
                <SkipForward className="w-5 h-5" />
              </button>
            </div>
            <div className="flex items-center gap-2 w-full">
              <span className="text-xs text-white/50 w-10 text-right">
                {formatDuration(Math.floor(currentTime))}
              </span>
              <input
                type="range"
                min={0}
                max={duration || 100}
                value={currentTime}
                onChange={(e) => seekPlayback(Number(e.target.value))}
                className="flex-1 h-1 accent-accent cursor-pointer"
              />
              <span className="text-xs text-white/50 w-10">
                {formatDuration(Math.floor(duration))}
              </span>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
