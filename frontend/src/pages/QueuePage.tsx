import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { MobileHeader } from '@/components/MobileHeader';
import { QueueSection } from '@/components/QueueSection';
import { QueueRefreshPanel } from '@/components/QueueRefreshPanel';
import { usePlayerStore } from '@/stores/playerStore';
import type { QueueRefreshOptions } from '@/lib/api';

export default function QueuePage() {
  const [seeds, setSeeds] = useState<string[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const refreshQueueFromSearch = usePlayerStore((s) => s.refreshQueueFromSearch);
  const refreshQueueFromPreferences = usePlayerStore((s) => s.refreshQueueFromPreferences);
  const clearActiveSearchQuery = usePlayerStore((s) => s.clearActiveSearchQuery);
  const refreshQueueInBackground = usePlayerStore((s) => s.refreshQueueInBackground);
  const queueBuilding = usePlayerStore((s) => s.queueBuilding);

  useEffect(() => {
    // Cached queue is already in the store; reconcile with server in the background.
    void refreshQueueInBackground();
  }, [refreshQueueInBackground]);

  const handleRefresh = async (nextSeeds: string[] | null, options: QueueRefreshOptions) => {
    if (usePlayerStore.getState().playbackMode === 'playlist') {
      toast.error('Exit playlist mode first — play from Home or Search');
      return;
    }
    setRefreshing(true);
    toast('Rebuilding your queue…', { icon: '⏳' });
    try {
      if (nextSeeds?.length) {
        await refreshQueueFromSearch(nextSeeds, options);
        toast.success(
          nextSeeds.length === 1
            ? 'Queue updated from your search'
            : `Queue mixed from ${nextSeeds.length} seeds`,
        );
      } else {
        await refreshQueueFromPreferences(options);
        setSeeds([]);
        toast.success('Queue refreshed from your preferences');
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Could not refresh queue';
      toast.error(message);
    } finally {
      setRefreshing(false);
    }
  };

  const handleClearSeeds = async () => {
    setSeeds([]);
    await clearActiveSearchQuery();
    toast.success('Queue will use random discovery again');
  };

  return (
    <div className="space-y-6 max-w-3xl pb-4">
      <MobileHeader title="Queue" showYoutubeDiscoveryToggle />
      <h2 className="hidden md:block text-2xl font-bold">Queue</h2>

      {queueBuilding && (
        <p className="text-xs text-accent/90 flex items-center gap-2 glass px-3 py-2 rounded-lg">
          <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
          Building your discovery queue in the background…
        </p>
      )}

      <QueueRefreshPanel
        seeds={seeds}
        onSeedsChange={setSeeds}
        onRefresh={handleRefresh}
        refreshing={refreshing}
      />

      {seeds.length > 0 && (
        <button
          type="button"
          onClick={handleClearSeeds}
          className="text-xs text-white/50 hover:text-white underline"
        >
          Clear active search seeds
        </button>
      )}

      <QueueSection showRefresh={false} />
    </div>
  );
}
