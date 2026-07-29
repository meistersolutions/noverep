import { Library, Youtube } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '@/lib/api';
import { usePlayerStore } from '@/stores/playerStore';

export function useYoutubeDiscoveryEnabled(): boolean {
  const preferences = usePlayerStore((s) => s.preferences);
  return preferences?.discovery_youtube_enabled ?? true;
}

export function YoutubeDiscoveryToggle({ compact = false }: { compact?: boolean }) {
  const preferences = usePlayerStore((s) => s.preferences);
  const enabled = useYoutubeDiscoveryEnabled();

  if (!preferences) return null;

  const toggle = async () => {
    const next = !enabled;
    try {
      const updated = await api.updatePreferences({ discovery_youtube_enabled: next });
      usePlayerStore.setState({ preferences: updated });
      toast.success(
        next ? 'YouTube discovery on' : 'Library-only queue (YouTube for playback)',
      );
    } catch {
      toast.error('Could not update YouTube discovery');
    }
  };

  const title = enabled
    ? 'YouTube discovery is on — queue mixes library + YouTube search'
    : 'Library only — songs from Songs Library; YouTube used only to play';

  if (compact) {
    return (
      <button
        type="button"
        onClick={toggle}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors touch-manipulation shrink-0 ${
          enabled ? 'bg-accent/20 text-accent' : 'bg-white/10 text-white/70'
        }`}
        title={title}
        aria-pressed={enabled}
        aria-label={enabled ? 'YouTube discovery on' : 'YouTube discovery off'}
      >
        {enabled ? <Youtube className="w-3.5 h-3.5" /> : <Library className="w-3.5 h-3.5" />}
        {enabled ? 'YT on' : 'Library'}
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={toggle}
      className={`text-xs px-3 py-1.5 rounded-lg border transition-colors touch-manipulation ${
        enabled
          ? 'border-accent/50 bg-accent/15 text-accent'
          : 'border-white/15 bg-white/5 text-white/70'
      }`}
      title={title}
      aria-pressed={enabled}
    >
      {enabled ? 'YouTube discovery: ON' : 'YouTube discovery: OFF (library only)'}
    </button>
  );
}
