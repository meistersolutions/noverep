import { useCallback, useId, useMemo } from 'react';

export const POPULARITY_MIN = 1;
export const POPULARITY_MAX = 100;

interface PopularityRangeSliderProps {
  min: number;
  max: number;
  onChange: (min: number, max: number) => void;
}

function clampPopularity(value: number): number {
  return Math.min(POPULARITY_MAX, Math.max(POPULARITY_MIN, Math.round(value)));
}

export function PopularityRangeSlider({ min, max, onChange }: PopularityRangeSliderProps) {
  const id = useId();
  const lo = clampPopularity(Math.min(min, max));
  const hi = clampPopularity(Math.max(min, max));
  const span = POPULARITY_MAX - POPULARITY_MIN;

  const fillStyle = useMemo(() => {
    const left = ((lo - POPULARITY_MIN) / span) * 100;
    const right = ((hi - POPULARITY_MIN) / span) * 100;
    return {
      left: `${left}%`,
      width: `${Math.max(0, right - left)}%`,
    };
  }, [hi, lo, span]);

  const setLow = useCallback(
    (raw: number) => {
      const next = clampPopularity(raw);
      onChange(Math.min(next, hi), hi);
    },
    [hi, onChange],
  );

  const setHigh = useCallback(
    (raw: number) => {
      const next = clampPopularity(raw);
      onChange(lo, Math.max(next, lo));
    },
    [lo, onChange],
  );

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm text-white/70">
          Score <span className="font-semibold text-white">{lo}</span>
          <span className="text-white/40"> – </span>
          <span className="font-semibold text-white">{hi}</span>
        </p>
        <p className="text-xs text-white/40">1 = obscure · 100 = hit</p>
      </div>

      <div className="relative h-8 select-none touch-manipulation">
        <div className="absolute left-0 right-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-white/10" />
        <div
          className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-accent"
          style={fillStyle}
        />
        <input
          id={`${id}-min`}
          type="range"
          min={POPULARITY_MIN}
          max={POPULARITY_MAX}
          step={1}
          value={lo}
          onChange={(e) => setLow(Number(e.target.value))}
          aria-label="Minimum popularity"
          className="popularity-range-thumb"
          style={{ zIndex: lo > span * 0.5 ? 5 : 3 }}
        />
        <input
          id={`${id}-max`}
          type="range"
          min={POPULARITY_MIN}
          max={POPULARITY_MAX}
          step={1}
          value={hi}
          onChange={(e) => setHigh(Number(e.target.value))}
          aria-label="Maximum popularity"
          className="popularity-range-thumb"
          style={{ zIndex: 4 }}
        />
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-md border border-white/10 px-2.5 py-1 text-xs text-white/60 hover:bg-white/5 hover:text-white"
          onClick={() => onChange(1, 100)}
        >
          All
        </button>
        <button
          type="button"
          className="rounded-md border border-white/10 px-2.5 py-1 text-xs text-white/60 hover:bg-white/5 hover:text-white"
          onClick={() => onChange(30, 50)}
        >
          Hidden gems
        </button>
        <button
          type="button"
          className="rounded-md border border-white/10 px-2.5 py-1 text-xs text-white/60 hover:bg-white/5 hover:text-white"
          onClick={() => onChange(80, 100)}
        >
          Popular hits
        </button>
      </div>
    </div>
  );
}
