import { useEffect, useState } from 'react';
import { api, SongDetails } from '@/lib/api';
import {
  getCachedTrackDetails,
  setCachedTrackDetails,
  trackCacheKey,
} from '@/lib/trackMetadataCache';

interface SongDetailsPanelProps {
  provider: string;
  providerTrackId: string;
  title?: string;
  artist?: string;
}

export function SongDetailsPanel({
  provider,
  providerTrackId,
  title,
  artist,
}: SongDetailsPanelProps) {
  const cacheKey = trackCacheKey(provider, providerTrackId);
  const [details, setDetails] = useState<SongDetails | null>(
    () => getCachedTrackDetails(cacheKey) ?? null,
  );
  const [loading, setLoading] = useState(() => !getCachedTrackDetails(cacheKey));

  useEffect(() => {
    const cached = getCachedTrackDetails(cacheKey);
    if (cached) {
      setDetails(cached);
      setLoading(false);
    } else {
      setLoading(true);
    }

    let cancelled = false;

    api
      .getTrackDetails(provider, providerTrackId, false, title, artist)
      .then((data) => {
        if (cancelled) return;
        setCachedTrackDetails(cacheKey, data);
        setDetails(data);
      })
      .catch(() => {
        if (!cancelled && !cached) setDetails(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [cacheKey, provider, providerTrackId, title, artist]);

  if (loading && !details) {
    return (
      <div className="w-full max-w-md mt-6 glass rounded-xl p-4 text-sm text-white/40">
        Loading song details…
      </div>
    );
  }

  if (!details) return null;

  const rows = [
    { label: 'Song', value: details.song_name },
    { label: 'Composed by', value: details.composed_by?.join(', ') },
    { label: 'Lyricist', value: details.lyricist_by?.join(', ') },
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
