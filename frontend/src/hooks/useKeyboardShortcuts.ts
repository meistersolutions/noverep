import { useEffect } from 'react';
import { usePlayerStore } from '@/stores/playerStore';

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) return true;
  return target.isContentEditable;
}

export function useKeyboardShortcuts() {
  const setPlaying = usePlayerStore((s) => s.setPlaying);
  const isPlaying = usePlayerStore((s) => s.isPlaying);
  const next = usePlayerStore((s) => s.next);
  const previous = usePlayerStore((s) => s.previous);
  const setVolume = usePlayerStore((s) => s.setVolume);
  const volume = usePlayerStore((s) => s.volume);
  const currentTrack = usePlayerStore((s) => s.currentTrack);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (isTypingTarget(e.target)) return;

      switch (e.code) {
        case 'Space':
        case 'MediaPlayPause':
          e.preventDefault();
          if (currentTrack) setPlaying(!isPlaying);
          break;
        case 'MediaPlay':
          e.preventDefault();
          if (currentTrack) setPlaying(true);
          break;
        case 'MediaPause':
          e.preventDefault();
          setPlaying(false);
          break;
        case 'ArrowRight':
        case 'MediaTrackNext':
          if (e.code === 'ArrowRight' && !e.shiftKey) break;
          e.preventDefault();
          next();
          break;
        case 'ArrowLeft':
        case 'MediaTrackPrevious':
          if (e.code === 'ArrowLeft' && !e.shiftKey) break;
          e.preventDefault();
          previous();
          break;
        case 'ArrowUp':
          e.preventDefault();
          setVolume(Math.min(1, volume + 0.05));
          break;
        case 'ArrowDown':
          e.preventDefault();
          setVolume(Math.max(0, volume - 0.05));
          break;
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isPlaying, setPlaying, next, previous, setVolume, volume, currentTrack]);
}
