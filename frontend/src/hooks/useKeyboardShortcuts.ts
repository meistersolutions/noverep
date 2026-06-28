import { useEffect } from 'react';
import { usePlayerStore } from '@/stores/playerStore';

export function useKeyboardShortcuts() {
  const { setPlaying, isPlaying, next, previous, setVolume, volume } = usePlayerStore();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      switch (e.code) {
        case 'Space':
          e.preventDefault();
          setPlaying(!isPlaying);
          break;
        case 'ArrowRight':
          if (e.shiftKey) next();
          break;
        case 'ArrowLeft':
          if (e.shiftKey) previous();
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
  }, [isPlaying, setPlaying, next, previous, setVolume, volume]);
}
