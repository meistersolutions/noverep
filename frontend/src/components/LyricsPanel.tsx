import { useEffect, useMemo, useRef, useState } from 'react';
import { api, LyricsLine, Track } from '@/lib/api';
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
  const [lines, setLines] = useState<LyricsLine[]>([]);
  const [synced, setSynced] = useState(false);
  const [instrumental, setInstrumental] = useState(false);
  const [loading, setLoading] = useState(true);
  const [missing, setMissing] = useState(false);
  const currentTime = usePlayerStore((s) => s.currentTime);
  const containerRef = useRef<HTMLDivElement>(null);
  const lineRefs = useRef<(HTMLParagraphElement | null)[]>([]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setMissing(false);
    setLines([]);

    api
      .getTrackLyrics({
        provider: track.provider,
        provider_track_id: track.provider_track_id,
        title: track.title,
        artist: track.artist,
        album: track.album,
        duration_seconds: track.duration_seconds,
      })
      .then((data) => {
        if (cancelled) return;
        if (!data || (!data.lines.length && !data.instrumental)) {
          setMissing(true);
          return;
        }
        setLines(data.lines);
        setSynced(data.synced);
        setInstrumental(data.instrumental);
      })
      .catch(() => {
        if (!cancelled) setMissing(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [track.provider, track.provider_track_id, track.title, track.artist, track.album, track.duration_seconds]);

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

  if (missing) return null;

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
