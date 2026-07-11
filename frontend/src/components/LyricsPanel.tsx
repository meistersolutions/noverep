import { useEffect, useMemo, useRef, useState } from 'react';
import { api, LyricsLine, Track } from '@/lib/api';
import {
  getCachedTrackDetails,
  getCachedTrackLyrics,
  setCachedTrackDetails,
  setCachedTrackLyrics,
  trackCacheKey,
} from '@/lib/trackMetadataCache';
import { usePlayerStore } from '@/stores/playerStore';

interface LyricsPanelProps {
  track: Track;
}

function activeLineIndex(lines: LyricsLine[], currentTimeSec: number): number {
  if (!lines.length) return -1;
  const nowMs = Math.floor(currentTimeSec * 1000);
  let active = 0;
  for (let i = 0; i < lines.length; i += 1) {
    if (lines[i].time_ms >= 0 && lines[i].time_ms <= nowMs) {
      active = i;
    }
  }
  return active;
}

export function LyricsPanel({ track }: LyricsPanelProps) {
  const cacheKey = trackCacheKey(track.provider, track.provider_track_id);
  const initialLyrics = getCachedTrackLyrics(cacheKey);
  const [lines, setLines] = useState<LyricsLine[]>(
    () => (initialLyrics && initialLyrics !== 'missing' ? initialLyrics.lines : []),
  );
  const [synced, setSynced] = useState(
    () => (initialLyrics && initialLyrics !== 'missing' ? initialLyrics.synced : false),
  );
  const [instrumental, setInstrumental] = useState(
    () => (initialLyrics && initialLyrics !== 'missing' ? initialLyrics.instrumental : false),
  );
  const [loading, setLoading] = useState(() => initialLyrics === undefined);
  const [missing, setMissing] = useState(() => initialLyrics === 'missing');
  const currentTime = usePlayerStore((s) => s.currentTime);
  const containerRef = useRef<HTMLDivElement>(null);
  const lineRefs = useRef<(HTMLParagraphElement | null)[]>([]);

    useEffect(() => {
    const cached = getCachedTrackLyrics(cacheKey);
    if (cached !== undefined) {
      if (cached === 'missing') {
        setMissing(true);
        setLines([]);
      } else {
        setLines(cached.lines);
        setSynced(cached.synced);
        setInstrumental(cached.instrumental);
        setMissing(false);
      }
      setLoading(false);
    } else {
      setLoading(true);
      setMissing(false);
      setLines([]);
    }

    let cancelled = false;

    const loadLyrics = async () => {
      const details = getCachedTrackDetails(cacheKey);
      let title = details?.song_name || track.title;
      let artist = details?.performed_by?.[0] || details?.artist || track.artist;
      let album = details?.movie_name || track.album;

      if (!details) {
        try {
          const enriched = await api.getTrackDetails(
            track.provider,
            track.provider_track_id,
            false,
            track.title,
            track.artist,
          );
          if (cancelled) return;
          setCachedTrackDetails(cacheKey, enriched);
          title = enriched.song_name || track.title;
          artist = enriched.performed_by?.[0] || enriched.artist || track.artist;
          album = enriched.movie_name || track.album;
        } catch {
          // Fall back to raw track metadata.
        }
      }

      if (cancelled) return;

      try {
        const data = await api.getTrackLyrics({
          provider: track.provider,
          provider_track_id: track.provider_track_id,
          title,
          artist,
          album,
          duration_seconds: track.duration_seconds,
        });
        if (cancelled) return;
        if (!data || (!data.lines.length && !data.instrumental)) {
          setCachedTrackLyrics(cacheKey, 'missing');
          setMissing(true);
          setLines([]);
          return;
        }
        setCachedTrackLyrics(cacheKey, data);
        setLines(data.lines);
        setSynced(data.synced);
        setInstrumental(data.instrumental);
        setMissing(false);
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : String(err);
          // Only cache permanent misses — transient API/network errors should retry next open.
          if (/not found|404/i.test(msg)) {
            setCachedTrackLyrics(cacheKey, 'missing');
          }
          setMissing(true);
          setLines([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void loadLyrics();

    return () => {
      cancelled = true;
    };
  }, [cacheKey, track.provider, track.provider_track_id, track.title, track.artist, track.album, track.duration_seconds]);

  const activeIdx = useMemo(
    () => (synced ? activeLineIndex(lines, currentTime) : -1),
    [lines, synced, currentTime],
  );

  useEffect(() => {
    if (activeIdx < 0) return;
    const node = lineRefs.current[activeIdx];
    node?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [activeIdx]);

  if (loading) {
    return (
      <div className="w-full max-w-md mt-6 glass rounded-xl p-4 text-sm text-white/40">
        Loading lyrics…
      </div>
    );
  }

  if (missing) {
    return (
      <div className="w-full max-w-md mt-6 glass rounded-xl p-4 text-sm text-white/40">
        Lyrics not available for this track
      </div>
    );
  }

  if (instrumental) {
    return (
      <div className="w-full max-w-md mt-6 glass rounded-xl p-4 text-sm text-white/50">
        Instrumental track
      </div>
    );
  }

  return (
    <div className="w-full max-w-md mt-6 glass rounded-xl p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-white/50 mb-3">
        Lyrics{synced ? '' : ' (unsynced)'}
      </h3>
      <div ref={containerRef} className="max-h-56 overflow-y-auto space-y-2 pr-1 lyrics-scroll">
        {lines.map((line, index) => (
          <p
            key={`${line.time_ms}-${index}`}
            ref={(el) => {
              lineRefs.current[index] = el;
            }}
            className={`text-sm leading-relaxed transition-colors ${
              index === activeIdx ? 'text-accent font-medium' : 'text-white/60'
            }`}
          >
            {line.text}
          </p>
        ))}
      </div>
    </div>
  );
}
