import { useEffect, useState } from 'react';
import { api, formatDuration } from '@/lib/api';
import { usePlayerStore } from '@/stores/playerStore';

interface HistoryEntry {
  id: string;
  title: string;
  artist: string;
  album: string | null;
  genre: string | null;
  provider: string;
  played_at: string;
  duration_listened: number;
  completion_pct: number;
  skipped: boolean;
}

export default function HistoryPage() {
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [exporting, setExporting] = useState(false);
  const historyVersion = usePlayerStore((s) => s.historyVersion);

  const load = () => api.getHistory().then(setHistory);
  const exportCsv = async () => {
    try {
      setExporting(true);
      const blob = await api.exportHistoryCsv();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'listening-history.csv';
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  };

  useEffect(() => {
    load();
  }, [historyVersion]);

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Listening History</h2>
        <div className="flex items-center gap-2">
          <button className="btn-ghost text-sm" onClick={load}>
            Refresh
          </button>
          <button
            className="btn-primary text-sm"
            onClick={exportCsv}
            disabled={exporting}
          >
            {exporting ? 'Exporting…' : 'Export CSV'}
          </button>
        </div>
      </div>
      <p className="text-white/50 text-sm">
        Every play is recorded to enforce your never-repeat memory window.
      </p>
      <div className="relative border-l border-white/10 ml-3 space-y-4">
        {history.map((entry) => (
          <div key={entry.id} className="relative pl-6">
            <div className="absolute -left-1.5 top-2 w-3 h-3 rounded-full bg-accent" />
            <div className="glass p-4">
              <div className="flex justify-between items-start">
                <div>
                  <p className="font-medium">{entry.title}</p>
                  <p className="text-sm text-white/50">{entry.artist}</p>
                </div>
                <span className="text-xs text-white/40 capitalize">{entry.provider}</span>
              </div>
              <div className="flex gap-4 mt-2 text-xs text-white/40">
                <span>{new Date(entry.played_at).toLocaleString()}</span>
                <span>{Math.round(entry.completion_pct)}% listened</span>
                <span>{formatDuration(entry.duration_listened)}</span>
                {entry.skipped && <span className="text-yellow-400">Skipped</span>}
              </div>
            </div>
          </div>
        ))}
        {history.length === 0 && (
          <p className="text-white/50 pl-6">No listening history yet. Play a song to get started.</p>
        )}
      </div>
    </div>
  );
}
