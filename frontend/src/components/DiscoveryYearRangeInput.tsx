import { useEffect, useState } from 'react';
import {
  DISCOVERY_YEAR_MAX,
  DISCOVERY_YEAR_MIN,
  validateYearField,
  validateYearRange,
  yearToInput,
} from '@/lib/yearValidation';

interface DiscoveryYearRangeInputProps {
  yearFrom: number | null;
  yearTo: number | null;
  onSave: (from: number | null, to: number | null) => void | Promise<void>;
  compact?: boolean;
}

export function DiscoveryYearRangeInput({
  yearFrom,
  yearTo,
  onSave,
  compact = false,
}: DiscoveryYearRangeInputProps) {
  const [fromText, setFromText] = useState(() => yearToInput(yearFrom));
  const [toText, setToText] = useState(() => yearToInput(yearTo));
  const [fromError, setFromError] = useState<string | null>(null);
  const [toError, setToError] = useState<string | null>(null);
  const [rangeError, setRangeError] = useState<string | null>(null);

  useEffect(() => {
    setFromText(yearToInput(yearFrom));
    setToText(yearToInput(yearTo));
    setFromError(null);
    setToError(null);
    setRangeError(null);
  }, [yearFrom, yearTo]);

  const commit = async (nextFromText: string, nextToText: string) => {
    const fromResult = validateYearField(nextFromText);
    const toResult = validateYearField(nextToText);

    setFromError(fromResult.error);
    setToError(toResult.error);

    if (fromResult.error || toResult.error) {
      setRangeError(null);
      return;
    }

    const rangeErr = validateYearRange(fromResult.value, toResult.value);
    setRangeError(rangeErr);
    if (rangeErr) return;

    const unchanged =
      fromResult.value === yearFrom && toResult.value === yearTo;
    if (unchanged) return;

    try {
      await onSave(fromResult.value, toResult.value);
    } catch {
      return;
    }
    setFromText(yearToInput(fromResult.value));
    setToText(yearToInput(toResult.value));
  };

  const inputClass = compact
    ? 'w-full bg-surface-raised border rounded-lg px-3 py-2 text-sm'
    : 'w-full bg-surface-raised border rounded-lg px-4 py-2';

  const border = (err: string | null) =>
    err ? 'border-red-500/60' : 'border-white/10';

  return (
    <div className="space-y-2">
      <div className={compact ? 'grid grid-cols-2 gap-2' : 'grid grid-cols-2 gap-3'}>
        <label className="space-y-1">
          <span className="text-sm text-white/60">From year</span>
          <input
            type="text"
            inputMode="numeric"
            autoComplete="off"
            placeholder="e.g. 2010"
            value={fromText}
            onChange={(e) => {
              setFromText(e.target.value);
              setFromError(null);
              setRangeError(null);
            }}
            onBlur={() => commit(fromText, toText)}
            className={`${inputClass} ${border(fromError)}`}
            aria-invalid={!!fromError}
          />
          {fromError && <p className="text-xs text-red-400">{fromError}</p>}
        </label>
        <label className="space-y-1">
          <span className="text-sm text-white/60">To year</span>
          <input
            type="text"
            inputMode="numeric"
            autoComplete="off"
            placeholder="e.g. 2020"
            value={toText}
            onChange={(e) => {
              setToText(e.target.value);
              setToError(null);
              setRangeError(null);
            }}
            onBlur={() => commit(fromText, toText)}
            className={`${inputClass} ${border(toError)}`}
            aria-invalid={!!toError}
          />
          {toError && <p className="text-xs text-red-400">{toError}</p>}
        </label>
      </div>
      {rangeError && <p className="text-xs text-red-400">{rangeError}</p>}
      <p className="text-xs text-white/40">
        Leave blank for any year ({DISCOVERY_YEAR_MIN}–{DISCOVERY_YEAR_MAX}). Saves when you leave the field.
      </p>
    </div>
  );
}
