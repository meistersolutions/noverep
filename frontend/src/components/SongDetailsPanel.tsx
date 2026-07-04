import { useEffect, useState } from 'react';
import { api, SongDetails } from '@/lib/api';

interface SongDetailsPanelProps {
  provider: string;
  providerTrackId: string;
}

export function SongDetailsPanel({ provider, providerTrackId }: SongDetailsPanelProps) {
  const [details, setDetails] = useState<SongDetails | null>(null);

  useEffect(() => {
    let cancelled = false;
    setDetails(null);

    api
      .getTrackDetails(provider, providerTrackId)
      .then((data) => {
        if (!cancelled) setDetails(data);
      })
      .catch(() => {
        if (!cancelled) setDetails(null);
      });

    return () => {
      cancelled = true;
    };
  }, [provider, providerTrackId]);

  if (!details) return null;

  const rows = [
    { label: 'Song', value: details.song_name },
    { label: 'Composed by', value: details.composed_by?.join(', ') },
    { label: 'Performed by', value: details.performed_by?.join(', ') || details.artist },
    { label: 'Movie', value: details.movie_name },
    { label: 'Year', value: details.release_year ? String(details.release_year) : null },
  ].filter((row) => row.value);

  if (!rows.length) return null;

  return (
    <div className="w-full max-w-md mt-6 glass rounded-xl p-4 space-y-2 text-sm">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-white/50">Song details</h3>
      {rows.map((row) => (
        <div key={row.label} className="flex gap-3">
          <span className="text-white/40 w-28 shrink-0">{row.label}</span>
          <span className="text-white/80">{row.value}</span>
        </div>
      ))}
    </div>
  );
}
