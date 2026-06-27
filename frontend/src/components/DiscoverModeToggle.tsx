import { Sparkles, RotateCcw } from 'lucide-react';
import { api } from '@/lib/api';
import { usePlayerStore } from '@/stores/playerStore';
import toast from 'react-hot-toast';

export function DiscoverModeToggle({ compact = false }: { compact?: boolean }) {
  const preferences = usePlayerStore((s) => s.preferences);
  const loadPreferences = usePlayerStore((s) => s.loadPreferences);

  if (!preferences) return null;

  const discoverOnly = !preferences.repeat_disabled;

  const toggle = async () => {
    try {
      await api.updatePreferences({ repeat_disabled: discoverOnly });
      await loadPreferences();
      toast.success(discoverOnly ? 'Including heard songs' : 'Discover new only');
    } catch {
      toast.error('Could not update mode');
    }
  };

  if (compact) {
    return (
      <button
        onClick={toggle}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
          discoverOnly
            ? 'bg-accent/20 text-accent'
            : 'bg-white/10 text-white/70'
        }`}
        title={discoverOnly ? 'Discover new songs only' : 'Include already heard songs'}
      >
        {discoverOnly ? <Sparkles className="w-3.5 h-3.5" /> : <RotateCcw className="w-3.5 h-3.5" />}
        {discoverOnly ? 'Discover' : 'All songs'}
      </button>
    );
  }

  return (
    <div className="glass p-4 flex items-center justify-between gap-4">
      <div>
        <p className="font-medium text-sm">Playback mode</p>
        <p className="text-xs text-white/50 mt-0.5">
          {discoverOnly
            ? 'Hiding songs you heard recently'
            : 'Showing all songs including heard ones'}
        </p>
      </div>
      <button
        onClick={toggle}
        className={`relative w-14 h-8 rounded-full transition-colors ${
          discoverOnly ? 'bg-accent' : 'bg-white/20'
        }`}
        aria-label="Toggle discover mode"
      >
        <span
          className={`absolute top-1 w-6 h-6 rounded-full bg-white shadow transition-transform ${
            discoverOnly ? 'left-7' : 'left-1'
          }`}
        />
      </button>
    </div>
  );
}

export function useDiscoverOnly(): boolean {
  const preferences = usePlayerStore((s) => s.preferences);
  return preferences ? !preferences.repeat_disabled : true;
}
